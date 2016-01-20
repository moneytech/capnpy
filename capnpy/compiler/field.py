from capnpy import schema
from capnpy.type import Types

@schema.Field.__extend__
class Field:

    def emit(self, m, node):
        name = m._field_name(self)
        union_check_done = self._emit(m, node, name)
        if not union_check_done and self.discriminantValue != Field.noDiscriminant:
            line = '{name} = _field.Union({discriminantValue}, {name})'
            m.w(line, name=name, discriminantValue=self.discriminantValue)


@schema.Field__Slot.__extend__
class Field__Slot:

    def _emit(self, m, node, name):
        if self.slot.type.is_bool():
            return self._emit_bool(m, name)
        #
        offset = self.slot.offset * self.slot.get_size()
        if self.slot.type.is_primitive():
            return self._emit_primitive(m, name, offset)
        elif self.slot.hadExplicitDefault:
            raise ValueError("explicit defaults not supported for field %s" % self)
        else:
            # a bit of metaprogramming: call _emit_text, _emit_struct, etc,
            # depending on the type
            #
            methname = '_emit_%s' % self.slot.type.which()
            _emit = getattr(self, methname, None)
            if _emit is None:
                raise NotImplementedError('Unknown type: %s' % self.slot.type)
            else:
                return _emit(m, name, offset)

    def _emit_primitive(self, m, name, offset):
        ns = m.code.new_scope()
        ns.offset = offset
        ns.typename = '_Types.%s' % self.slot.type.which()
        ns.default_ = self.slot.defaultValue.as_pyobj()
        ns.use_tag = self.discriminantValue != Field.noDiscriminant
        ns.tag = self.discriminantValue
        ns.ifmt = "ord(%r)" % self.slot.get_fmt()
        m.def_property(ns, name, """
            if {use_tag}: # "compile time" switch
                self._ensure_union({tag})
            value = self._read_data({offset}, {ifmt})
            if {default_} != 0:
                value = value ^ {default_}
            return value
        """)
        return True

    def _emit_bool(self, m, name):
        byteoffset, bitoffset = divmod(self.slot.offset, 8)
        default = self.slot.defaultValue.as_pyobj()
        m.w('{name} = _field.Bool("{name}", {byteoffset}, {bitoffset}, {default})',
            name=name, byteoffset=byteoffset, bitoffset=bitoffset, default=default)

    def _emit_text(self, m, name, offset):
        ns = m.code.new_scope()
        ns.name = name
        ns.offset = offset
        ns.w('{name} = _field.String("{name}", {offset})')
        self._emit_has_method(ns)

    def _emit_data(self, m, name, offset):
        ns = m.code.new_scope()
        ns.name = name
        ns.offset = offset
        ns.w('{name} = _field.Data("{name}", {offset})')
        self._emit_has_method(ns)

    def _emit_struct(self, m, name, offset):
        ns = m.code.new_scope()
        ns.name = name
        ns.offset = offset
        ns.structname = self.slot.type.compile_name(m)
        ns.w('{name} = _field.Struct("{name}", {offset}, {structname})')
        self._emit_has_method(ns)

    def _emit_list(self, m, name, offset):
        ns = m.code.new_scope()
        ns.name = name
        ns.offset = offset
        ns.itemtype = self.slot.type.list.elementType.compile_name(m)
        ns.w('{name} = _field.List("{name}", {offset}, {itemtype})')
        self._emit_has_method(ns)

    def _emit_has_method(self, ns):
        ns.ww("""
            def has_{name}(self):
                offset, ptr = self._read_ptr({offset})
                return ptr != 0

        """)

    def _emit_enum(self, m, name, offset):
        enumname = self.slot.type.compile_name(m)
        m.w('{name} = _field.Enum("{name}", {offset}, {enumname})',
            name=name, offset=offset, enumname=enumname)
        
    def _emit_void(self, m, name, offset):
        m.w('{name} = _field.Void("{name}")', name=name)
        
    def _emit_anyPointer(self, m, name, offset):
        m.w('{name} = _field.AnyPointer("{name}", {offset})', name=name, offset=offset)


@schema.Field__Group.__extend__
class Field__Group:

    def _emit(self, m, node, name):
        groupnode = m.allnodes[self.group.typeId]
        ns = m.code.new_scope()
        ns.name = name
        ns.clsname = groupnode.compile_name(m)
        if self.is_nullable(m):
            ns.privname = '_' + name
            ns.ww("""
                {privname} = _field.Group({clsname})
                @property
                def {name}(self):
                    if self.{privname}.is_null:
                        return None
                    return self.{privname}.value
            """)
        else:
            ns.w('{name} = _field.Group({clsname})')
