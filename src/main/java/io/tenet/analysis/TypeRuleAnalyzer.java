package io.tenet.analysis;

import com.sun.source.tree.ClassTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.TreePath;
import com.sun.source.util.Trees;
import io.tenet.model.RuleId;

import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.Modifier;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.lang.model.type.DeclaredType;
import javax.lang.model.type.TypeKind;
import javax.lang.model.type.TypeMirror;
import javax.lang.model.util.Elements;
import java.util.Set;
import java.util.regex.Pattern;

final class TypeRuleAnalyzer {
    private static final Pattern MUTABLE_REASON = Pattern.compile("[A-Za-z0-9].{8,98}\\.");
    private final Trees trees;
    private final Elements elements;
    private final CompilationContext context;

    TypeRuleAnalyzer(final Trees trees, final Elements elements, final CompilationContext context) {
        this.trees = trees;
        this.elements = elements;
        this.context = context;
    }

    void analyze(final TreePath classPath, final ClassTree type, final TypeElement element) {
        analyzeDependencies(classPath, type, element);
        analyzeFields(classPath, type);
        analyzePublicSurface(classPath, type, element);
        analyzeInheritance(type, element);
        new CohesionAnalyzer(trees, context).analyze(classPath, type);
    }

    private void analyzeDependencies(
            final TreePath classPath,
            final ClassTree type,
            final TypeElement element) {
        final String owner = element.getQualifiedName().toString();
        final DependencyCollector collector = new DependencyCollector(trees, type, owner);
        collector.scan(classPath, null);
        final Set<String> dependencies = collector.dependencies();
        final int maximum = context.config().rules().integer("max.typeFanOut");
        if (dependencies.size() > maximum) {
            context.add(
                    RuleId.TYPE_FAN_OUT,
                    type,
                    "Type depends on " + dependencies.size() + " external types",
                    "maximum=" + maximum);
        }
        context.facts().typeDependencies().add(new TypeDependencies(
                owner,
                elements.getPackageOf(element).getQualifiedName().toString(),
                context.source(),
                Location.of(context.unit(), context.positions(), type),
                dependencies));
    }

    private void analyzeFields(final TreePath classPath, final ClassTree type) {
        for (final Tree member : type.getMembers()) {
            if (member instanceof VariableTree field) {
                analyzeField(new TreePath(classPath, field), field);
            }
        }
    }

    private void analyzeField(final TreePath fieldPath, final VariableTree field) {
        final Element element = trees.getElement(fieldPath);
        if (element == null || element.getKind() == ElementKind.ENUM_CONSTANT) {
            return;
        }
        if (!element.getModifiers().contains(Modifier.FINAL) && !hasValidMutableStateReason(element)) {
            context.add(
                    RuleId.MUTABLE_FIELD,
                    field,
                    "Field `" + field.getName() + "` must be final",
                    "use final or @MutableState with a 9-99 character reason sentence");
        }
        final boolean constant = element instanceof VariableElement variable && variable.getConstantValue() != null;
        if (element.getModifiers().contains(Modifier.PUBLIC) && !constant) {
            context.add(
                    RuleId.PUBLIC_FIELD,
                    field,
                    "Field `" + field.getName() + "` must not be public",
                    "expose behavior through a narrow method contract");
        }
    }

    private void analyzePublicSurface(
            final TreePath classPath,
            final ClassTree type,
            final TypeElement element) {
        final int publicMethods = publicMethodCount(classPath, type, element);
        final int maximumPublicMethods = context.config().rules().integer("max.publicMethods");
        if (publicMethods > maximumPublicMethods) {
            context.add(
                    RuleId.PUBLIC_API_SURFACE,
                    type,
                    "Type exposes " + publicMethods + " public methods",
                    "maximum=" + maximumPublicMethods);
        }
        final int interfaceMethods = interfaceMethodCount(type, element);
        final int maximumInterfaceMethods = context.config().rules().integer("max.interfaceMethods");
        if (interfaceMethods > maximumInterfaceMethods) {
            context.add(
                    RuleId.INTERFACE_SURFACE,
                    type,
                    "Interface exposes " + interfaceMethods + " methods",
                    "maximum=" + maximumInterfaceMethods + "; split by client usage");
        }
    }

    private int publicMethodCount(
            final TreePath classPath,
            final ClassTree type,
            final TypeElement owner) {
        int count = 0;
        for (final Tree member : type.getMembers()) {
            if (!(member instanceof MethodTree method) || declaresOverride(method)) {
                continue;
            }
            final Element element = trees.getElement(new TreePath(classPath, method));
            if (element instanceof ExecutableElement executable
                    && executable.getModifiers().contains(Modifier.PUBLIC)
                    && !overridesMethod(executable, owner)) {
                count++;
            }
        }
        return count;
    }

    private static int interfaceMethodCount(final ClassTree type, final TypeElement element) {
        if (element.getKind() != ElementKind.INTERFACE) {
            return 0;
        }
        return (int) type.getMembers().stream()
                .filter(MethodTree.class::isInstance)
                .map(MethodTree.class::cast)
                .filter(method -> !method.getName().contentEquals("<init>"))
                .count();
    }

    private void analyzeInheritance(final ClassTree type, final TypeElement element) {
        final int depth = inheritanceDepth(element);
        final int maximum = context.config().rules().integer("max.inheritanceDepth");
        if (depth > maximum) {
            context.add(
                    RuleId.INHERITANCE_DEPTH,
                    type,
                    "Inheritance depth is " + depth,
                    "maximum=" + maximum + "; prefer composition");
        }
    }

    private static int inheritanceDepth(final TypeElement element) {
        int depth = 0;
        TypeMirror superclass = element.getSuperclass();
        while (superclass.getKind() == TypeKind.DECLARED) {
            final Element parentElement = ((DeclaredType) superclass).asElement();
            if (!(parentElement instanceof TypeElement parent)
                    || parent.getQualifiedName().contentEquals("java.lang.Object")) {
                break;
            }
            depth++;
            superclass = parent.getSuperclass();
        }
        return depth;
    }

    private boolean overridesMethod(final ExecutableElement method, final TypeElement owner) {
        return elements.getAllMembers(owner).stream()
                .filter(ExecutableElement.class::isInstance)
                .map(ExecutableElement.class::cast)
                .filter(candidate -> !candidate.equals(method))
                .anyMatch(candidate -> elements.overrides(method, candidate, owner));
    }

    private static boolean declaresOverride(final MethodTree method) {
        return method.getModifiers().getAnnotations().stream()
                .anyMatch(annotation -> annotation.getAnnotationType().toString().endsWith("Override"));
    }

    private static boolean hasValidMutableStateReason(final Element element) {
        return element.getAnnotationMirrors().stream()
                .filter(annotation -> annotation.getAnnotationType().toString().equals("io.tenet.api.MutableState"))
                .flatMap(annotation -> annotation.getElementValues().entrySet().stream())
                .filter(entry -> entry.getKey().getSimpleName().contentEquals("reason"))
                .map(entry -> entry.getValue().getValue())
                .filter(String.class::isInstance)
                .map(String.class::cast)
                .anyMatch(reason -> MUTABLE_REASON.matcher(reason).matches());
    }
}
