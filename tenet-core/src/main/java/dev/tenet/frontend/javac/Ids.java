package dev.tenet.frontend.javac;

import dev.tenet.facts.MethodId;
import dev.tenet.facts.TypeName;
import java.util.StringJoiner;
import javax.lang.model.element.Element;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.lang.model.util.Types;

final class Ids {

  private final Types types;

  Ids(Types types) {
    this.types = types;
  }

  TypeName typeName(TypeElement type) {
    return new TypeName(type.getQualifiedName().toString());
  }

  MethodId methodId(ExecutableElement method) {
    TypeElement owner = (TypeElement) method.getEnclosingElement();
    StringJoiner signature = new StringJoiner(",", "(", ")");
    for (VariableElement param : method.getParameters()) {
      signature.add(types.erasure(param.asType()).toString());
    }
    return new MethodId(typeName(owner), method.getSimpleName().toString(), signature.toString());
  }

  String erasedQName(javax.lang.model.type.TypeMirror type) {
    return types.erasure(type).toString();
  }

  static TypeElement enclosingType(Element element) {
    Element walk = element;
    while (walk != null && !(walk instanceof TypeElement)) {
      walk = walk.getEnclosingElement();
    }
    return (TypeElement) walk;
  }
}
