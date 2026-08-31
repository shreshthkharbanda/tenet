package dev.tenet.facts;

import dev.tenet.model.SourceRef;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public final class ClassFacts {

  public enum Kind {
    CLASS,
    INTERFACE,
    ENUM,
    RECORD,
    ANNOTATION
  }

  private final TypeName name;
  private final SourceRef site;
  private final Kind kind;
  private final Visibility visibility;
  private final boolean nested;
  private final boolean abstractType;
  private final List<FieldFacts> fields;
  private final List<MethodId> methods;
  private final List<MethodId> constructors;
  private final List<String> enumConstants;
  private final Optional<TypeName> superType;
  private final List<TypeName> interfaces;

  private ClassFacts(Builder b) {
    this.name = Objects.requireNonNull(b.name, "name");
    this.site = Objects.requireNonNull(b.site, "site");
    this.kind = Objects.requireNonNull(b.kind, "kind");
    this.visibility = Objects.requireNonNull(b.visibility, "visibility");
    this.nested = b.nested;
    this.abstractType = b.abstractType;
    this.fields = List.copyOf(b.fields);
    this.methods = List.copyOf(b.methods);
    this.constructors = List.copyOf(b.constructors);
    this.enumConstants = List.copyOf(b.enumConstants);
    this.superType = Optional.ofNullable(b.superType);
    this.interfaces = List.copyOf(b.interfaces);
  }

  public TypeName name() {
    return name;
  }

  public SourceRef site() {
    return site;
  }

  public Kind kind() {
    return kind;
  }

  public Visibility visibility() {
    return visibility;
  }

  public boolean isNested() {
    return nested;
  }

  public boolean isAbstract() {
    return abstractType;
  }

  public List<FieldFacts> fields() {
    return fields;
  }

  public List<MethodId> methods() {
    return methods;
  }

  public List<MethodId> constructors() {
    return constructors;
  }

  public List<String> enumConstants() {
    return enumConstants;
  }

  public Optional<TypeName> superType() {
    return superType;
  }

  public List<TypeName> interfaces() {
    return interfaces;
  }

  public List<FieldFacts> instanceFields() {
    return fields.stream().filter(f -> !f.isStatic()).toList();
  }

  public List<FieldFacts> booleanInstanceFields() {
    return instanceFields().stream().filter(FieldFacts::isBoolean).toList();
  }

  public String display() {
    return name.simple() + " (" + site + ")";
  }

  public static Builder builder(TypeName name, SourceRef site) {
    return new Builder(name, site);
  }

  public static final class Builder {
    private final TypeName name;
    private final SourceRef site;
    private Kind kind = Kind.CLASS;
    private Visibility visibility = Visibility.PACKAGE_PRIVATE;
    private boolean nested;
    private boolean abstractType;
    private final List<FieldFacts> fields = new java.util.ArrayList<>();
    private final List<MethodId> methods = new java.util.ArrayList<>();
    private final List<MethodId> constructors = new java.util.ArrayList<>();
    private final List<String> enumConstants = new java.util.ArrayList<>();
    private TypeName superType;
    private final List<TypeName> interfaces = new java.util.ArrayList<>();

    private Builder(TypeName name, SourceRef site) {
      this.name = name;
      this.site = site;
    }

    public Builder kind(Kind k) {
      this.kind = k;
      return this;
    }

    public Builder visibility(Visibility v) {
      this.visibility = v;
      return this;
    }

    public Builder nested(boolean v) {
      this.nested = v;
      return this;
    }

    public Builder abstractType(boolean v) {
      this.abstractType = v;
      return this;
    }

    public Builder addField(FieldFacts f) {
      this.fields.add(f);
      return this;
    }

    public Builder addMethod(MethodId m) {
      this.methods.add(m);
      return this;
    }

    public Builder addConstructor(MethodId c) {
      this.constructors.add(c);
      return this;
    }

    public Builder addEnumConstant(String c) {
      this.enumConstants.add(c);
      return this;
    }

    public Builder superType(TypeName t) {
      this.superType = t;
      return this;
    }

    public Builder addInterface(TypeName t) {
      this.interfaces.add(t);
      return this;
    }

    public ClassFacts build() {
      return new ClassFacts(this);
    }
  }
}
