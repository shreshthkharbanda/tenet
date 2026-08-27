package io.tenet.analysis;

import com.sun.source.tree.ClassTree;
import com.sun.source.tree.IdentifierTree;
import com.sun.source.tree.MemberSelectTree;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;

import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import java.util.LinkedHashSet;
import java.util.Set;

public final class DependencyCollector extends TreePathScanner<Void, Void> {
    private final Trees trees;
    private final ClassTree root;
    private final String owner;
    private final Set<String> dependencies = new LinkedHashSet<>();

    public DependencyCollector(final Trees trees, final ClassTree root, final String owner) {
        this.trees = trees;
        this.root = root;
        this.owner = owner;
    }

    @Override
    public Void visitClass(final ClassTree node, final Void unused) {
        return node == root ? super.visitClass(node, unused) : null;
    }

    @Override
    public Void visitIdentifier(final IdentifierTree node, final Void unused) {
        add(trees.getElement(getCurrentPath()));
        return super.visitIdentifier(node, unused);
    }

    @Override
    public Void visitMemberSelect(final MemberSelectTree node, final Void unused) {
        add(trees.getElement(getCurrentPath()));
        return super.visitMemberSelect(node, unused);
    }

    public Set<String> dependencies() {
        return Set.copyOf(dependencies);
    }

    private void add(final Element element) {
        TypeElement type = null;
        Element cursor = element;
        while (cursor != null) {
            if (cursor instanceof TypeElement typeElement) {
                type = typeElement;
                break;
            }
            cursor = cursor.getEnclosingElement();
        }
        if (type == null) {
            return;
        }
        final String qualifiedName = type.getQualifiedName().toString();
        if (!qualifiedName.equals(owner) && !isPlatformType(qualifiedName)) {
            dependencies.add(qualifiedName);
        }
    }

    private static boolean isPlatformType(final String qualifiedName) {
        return qualifiedName.startsWith("java.")
                || qualifiedName.startsWith("javax.")
                || qualifiedName.startsWith("jdk.")
                || qualifiedName.startsWith("sun.");
    }
}

