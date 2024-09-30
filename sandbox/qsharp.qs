import Microsoft.Quantum.Arrays.Zipped;
import Microsoft.Quantum.Arrays.Mapped;
import Microsoft.Quantum.Arrays.ForEach;
// operation PrepareZero() : Qubit {
//     use q = Qubit();
//     return q;
// }

// operation PreparePlus() : Qubit {
//     use q = Qubit();
//     H(q);
//     return q;
// }


operation MSt(block : Qubit[], basis : (Qubit -> Unit is Ctl)[], ancilla : Qubit) : Unit {
    H(ancilla);

    for idx in 0..Length(basis) - 1 {
        let op = basis[idx];
        Controlled op([block[idx]], ancilla);
    }

    H(ancilla);
}

operation SyndromeExtraction(block : Qubit[], stabilizers : (Qubit -> Unit is Adj + Ctl)[][], ancillas : Qubit[]) : Unit {
    for i in 0..Length(stabilizers) -1 {
        MSt(block, stabilizers[i], ancillas[i]);
    }
}

function plus(x : Result, y : Result) : Result {
    if (x == One and y == One) {
        return Zero;
    }
    if (x == Zero and y == Zero) {
        return Zero;
    }

    return One;
}

function Plus(x : Result[], y : Result[]) : Result[] {
    return Mapped(plus, Zipped(x, y));
}

function Decode(syndrome : Result[]) : Pauli[] {
    if (syndrome == [Zero, Zero]) {
        return [PauliI, PauliI, PauliI];
    }

    if (syndrome == [One, Zero]) {
        return [PauliI, PauliX, PauliI];
    }

    if (syndrome == [Zero, One]) {
        return [PauliI, PauliI, PauliX];
    }

    return [PauliX, PauliI, PauliI];
}

function conjugate_one(p : Pauli, by : Pauli) : (Pauli, Int) {
    if (p == PauliI) {
        return (p, 0);
    }

    if (by == PauliI) {
        return (p, 0);
    }

    if (p == by) {
        return (p, 0);
    } else {
        return (p, 1);
    }
}

function conjugate_group(p : Pauli[], by : Pauli[]) : (Pauli[], Int) {
    let args = Zipped(p, by);
    let mapped = Mapped(conjugate_one, Zipped(p, by));

    mutable sign = 0;
    mutable pauli = [];
    for m in mapped {
        let (p, t) = m;
        set sign = (sign + t) % 2;
        set pauli += [p];
    }

    return (pauli, sign);
}

function conjugate(stabilizers : Pauli[][], correction : Pauli[]) : (Pauli[][], Int) {
    mutable sign = 0;
    mutable generator = [];
    for g in stabilizers {
        let (p, t) = conjugate_group(g, correction);
        set sign = (sign + t) % 2;
        set generator += [p];
    }

    return (generator, sign);
}

operation Main() : Result[][] {
    use b1 = Qubit[3];
    use b2 = Qubit[3];

    let stabilizers = [
        [PauliZ, PauliZ, PauliI],
        [PauliZ, PauliI, PauliZ]
    ];
    let X_l = [PauliX, PauliX, PauliX];
    let Z_l = [PauliZ, PauliI, PauliI];

    let blocks = [b1, b2];
    let correction = [PauliI, PauliI, PauliI];

    // ApplyPauli(X_l, b1);
    // X(b1[0]);

    // SyndromeExtraction(b1, stabilizers, ancillas);
    let s1_1 = [
        Measure(stabilizers[0], b1),
        Measure(stabilizers[1], b1),
    ];
    let s2_1 = [
        Measure(stabilizers[0], b2),
        Measure(stabilizers[1], b2),
    ];
    let b1_correction = Decode(s1_1);
    let b2_correction = Decode(s2_1);
    // ApplyPauli(correction, b1);

    // let (stabilizers, sign) = conjugate(stabilizers, correction);

    // let stabilizers = [
    //     [PauliZ, PauliY, PauliI],
    //     [PauliZ, PauliX, PauliZ]
    // ];
    // let X_l = [PauliX, PauliY, PauliX];
    // let Z_l = [PauliZ, PauliX, PauliI];

    // // Apply H
    // H(b1[0]);
    // CX(b1[0], b1[1]);
    // CX(b1[0], b1[2]);
    let Z_l = [PauliX, PauliX, PauliX];
    let X_l = [PauliZ, PauliI, PauliI];


    X(b1[2]);


    // SyndromeExtraction(b1, stabilizers, ancillas);
    let s2 = [
        Measure(stabilizers[0], b1),
        Measure(stabilizers[1], b1),
    ];
    let correction = Decode(s2);
    ApplyPauli(correction, b1);


    // X(b1[2]);
    // X(b1[1]);


    // ApplyPauli(correction, b1);
    let v = [
        Measure(Z_l, b1)
    ];

    for b in blocks {
        MResetEachZ(b1);
    }

    Message($"correction {correction}");
    return [s1, s2, v];
}
