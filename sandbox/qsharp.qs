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

operation Main() : Result[][] {
    use b1 = Qubit[3];

    let stabilizers = [
        [PauliZ, PauliZ, PauliI],
        [PauliZ, PauliI, PauliZ]
    ];
    let X_l = [PauliX, PauliX, PauliX];
    let Z_l = [PauliZ, PauliI, PauliI];

    let blocks = [b1];
    let correction = [PauliI, PauliI, PauliI];

    ApplyPauli(X_l, b1);
    // X(b1[1]);

    // SyndromeExtraction(b1, stabilizers, ancillas);
    let s1 = [
        Measure(stabilizers[0], b1),
        Measure(stabilizers[1], b1),
    ];
    let correction = Decode(s1);
    ApplyPauli(correction, b1);

    // let stabilizers = [
    //     [PauliZ, PauliY, PauliI],
    //     [PauliZ, PauliX, PauliZ]
    // ];
    // let X_l = [PauliX, PauliY, PauliX];
    // let Z_l = [PauliZ, PauliX, PauliI];

    // X(b1[2]);

    // Apply H
    // H(b1[0]);
    // CX(b1[0], b1[1]);
    // CX(b1[0], b1[2]);

    // SyndromeExtraction(b1, stabilizers, ancillas);
    let s2 = [
        Measure(stabilizers[0], b1),
        Measure(stabilizers[1], b1),
    ];
    let correction = Decode(s2);
    ApplyPauli(correction, b1);


    // X(b1[2]);
    // X(b1[1]);


    ApplyPauli(correction, b1);
    let v = [
        Measure(Z_l, b1)
    ];



    for b in blocks {
        MResetEachZ(b1);
    }

    Message($"correction {correction}");
    return [s1, s2, v];
}
