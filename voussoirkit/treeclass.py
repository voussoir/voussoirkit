class ExistingChild(Exception):
    pass

class InvalidIdentifier(Exception):
    pass

class Tree:
    def __init__(self, identifier, data=None):
        self.assert_identifier_ok(identifier)
        self.identifier = identifier
        self.data = data
        self.parent = None
        self.children = {}

    def __eq__(self, other):
        return isinstance(other, Tree) and self.abspath() == other.abspath()

    def __getitem__(self, key):
        return self.children[key]

    def __hash__(self):
        return hash(self.abspath())

    def __repr__(self):
        return f'Tree({self.identifier})'

    @staticmethod
    def assert_identifier_ok(identifier):
        if not isinstance(identifier, str):
            raise InvalidIdentifier(f'Identifier {identifier} must be a string.')

        if '/' in identifier or '\\' in identifier:
            raise InvalidIdentifier('Identifier cannot contain slashes')

    def abspath(self):
        node = self
        nodes = [node]
        while nodes[-1].parent is not None:
            nodes.append(nodes[-1].parent)
        nodes.reverse()
        nodes = [node.identifier for node in nodes]
        return '\\'.join(nodes)

    def add_child(self, other_node, overwrite_parent=False):
        self.assert_child_available(other_node.identifier)
        if other_node.parent is not None and not overwrite_parent:
            raise ValueError('That node already has a parent. Try `overwrite_parent=True`')

        other_node.parent = self
        self.children[other_node.identifier] = other_node
        return other_node

    def assert_child_available(self, identifier):
        if identifier in self.children:
            raise ExistingChild(f'Node {self.identifier} already has child {identifier}')

    def detach(self):
        if self.parent is None:
            return

        del self.parent.children[self.identifier]
        self.parent = None

    def list_children(self, sort=None):
        children = list(self.children.values())
        if sort is None:
            children.sort(key=lambda node: (node.identifier.lower(), node.identifier))
        else:
            children.sort(key=sort)
        return children

    def walk(self, sort=None):
        yield self
        for child in self.list_children(sort=sort):
            yield from child.walk(sort=sort)

    def walk_parents(self):
        parent = self.parent
        while parent is not None:
            yield parent
            parent = parent.parent
