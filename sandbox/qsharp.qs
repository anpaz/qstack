operation PrepareZero() : Qubit {
    use q = Qubit();
    return q;
}

operation PreparePlus() : Qubit {
    use q = Qubit();
    H(q);
    return q;
}

operation Main() : (Result, Result[]) {
    // Create a Bell state
    // let q1 = PreparePlus();
    // let q2 = PrepareZero();
    use q = Qubit[4];
    use ancilla = Qubit();

    H(q[3]);
    CNOT(q[3], q[0]);
    CNOT(q[0], q[1]);
    CNOT(q[1], q[2]);

    CNOT(q[2], ancilla);
    CNOT(q[3], ancilla);

    ApplyToEachCA(X, q);
    
    // X(q[1]);
    // CNOT(q[3], q[0]);
    // CNOT(q[3], q[1]);

    return (MResetZ(ancilla), MResetEachZ(q));
}
