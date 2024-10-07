# %%
from dataclasses import dataclass


@dataclass(frozen=True)
class Pauli:
    sign: int
    x: bool  # True for Pauli-X
    z: bool  # True for Pauli-Z

    def __mul__(self, other):
        assert isinstance(other, Pauli), "Can only multiply Pauli with another Pauli"
        if self == other:
            return I
        elif self == I:
            return other
        elif other == I:
            return self
        else:
            a = abs(self)
            b = abs(other)
            if a == b:
                return I
            if (X, Y) == (a, b):
                sign = (self.sign + other.sign + 1) % 4
                return Pauli(sign, False, True)
            elif (X, Z) == (a, b):
                sign = (self.sign + other.sign + 1) % 4
                return Pauli(sign, True, True)
            elif (Y, Z) == (a, b):
                sign = (self.sign + other.sign + 1) % 4
                return Pauli(sign, True, False)
            elif (Y, X) == (a, b):
                sign = (self.sign + other.sign + 3) % 4
                return Pauli(sign, False, True)
            elif (Z, X) == (a, b):
                sign = (self.sign + other.sign + 3) % 4
                return Pauli(sign, True, True)
            elif (Z, Y) == (a, b):
                sign = (self.sign + other.sign + 3) % 4
                return Pauli(sign, True, False)
            else:
                assert False, "Missing case? {self}, {other}"

    def __abs__(self):
        return Pauli(0, self.x, self.z)

    def __repr__(self) -> str:
        signs = ["", "i", "-", "-i"]
        s = signs[self.sign]
        if self.x and self.z:
            l = "Y"
        elif self.z:
            l = "Z"
        elif self.x:
            l = "X"
        else:
            l = "I"
        return f"{s}{l}"


def commutes(a: Pauli, b: Pauli):
    return a == b or a == I or b == I or abs(a) == abs(b)


def by_x(env: list[Pauli], idx: int) -> Pauli:
    pauli = env[idx]
    new_sign = pauli.sign
    if pauli.z:
        new_sign = (new_sign + 2) % 4
    env[idx] = Pauli(new_sign, pauli.x, pauli.z)
    return env


def by_y(env: list[Pauli], idx: int) -> Pauli:
    pauli = env[idx]
    new_sign = pauli.sign
    if pauli.z ^ pauli.x:
        new_sign = (new_sign + 2) % 4
    env[idx] = Pauli(new_sign, pauli.x, pauli.z)
    return env


def by_z(env: list[Pauli], idx: int) -> Pauli:
    pauli = env[idx]
    new_sign = pauli.sign
    if pauli.x:
        new_sign = (new_sign + 2) % 4
    env[idx] = Pauli(new_sign, pauli.x, pauli.z)
    return env


def by_h(stabilizer: tuple[Pauli], idx: int) -> Pauli:
    pauli = stabilizer[idx]
    new_sign = pauli.sign
    if pauli.x and pauli.z:
        new_sign = (new_sign + 2) % 4
    new_stabilizer = []
    for j in range(len(stabilizer)):
        if j == idx:
            new_stabilizer.append(Pauli(new_sign, pauli.z, pauli.x))
        else:
            new_stabilizer.append(stabilizer[j])
    return new_stabilizer


def by_cx(stabilizer: list[Pauli], ctl: int, tgt: int):
    assert ctl < len(stabilizer), f"Invalid ctl index, ctl:{ctl}, tgt:{tgt} for pauli of length({len(stabilizer)})"
    assert tgt < len(stabilizer), f"Invalid tgt index, ctl:{ctl}, tgt:{tgt} for pauli of length({len(stabilizer)})"

    c = stabilizer[ctl]
    t = stabilizer[tgt]

    new_ctl = Pauli(c.sign, c.x, c.z ^ t.z)
    new_tgt = Pauli(t.sign, t.x ^ c.x, t.z)

    new_stabilizer = []
    for j in range(len(stabilizer)):
        if j == ctl:
            new_stabilizer.append(new_ctl)
        elif j == tgt:
            new_stabilizer.append(new_tgt)
        else:
            new_stabilizer.append(stabilizer[j])

    return new_stabilizer


I = Pauli(0, False, False)

X = Pauli(0, True, False)
Y = Pauli(0, True, True)
Z = Pauli(0, False, True)

# %%
a = Z * Y
a * a

# %%
