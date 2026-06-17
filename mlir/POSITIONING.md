# qstack: Positioning

## Elevator pitch

**qstack is a construction kit for trustworthy quantum compilers.** Quantum error correction is what will make quantum
computers reliable, but the compilers that produce it are huge, intricate, and impossible to test, and a single bug
silently corrupts results in a way that looks exactly like hardware noise. qstack makes these compilers _provably
correct_. Crucially, it also makes that trust **reusable**: a new error-correction code is a plug-in package, and when
you stack codes together to make a stronger one, their correctness guarantees stack automatically. Verify the building
blocks once; snap them together; trust comes along for free.

## The problem

To run a useful quantum program you wrap each "logical" qubit in **quantum error correction (QEC)**: many physical
qubits, constant measurement, and classical feedback that fixes errors on the fly. A compiler turns a clean logical
program into this sprawling machinery, where one logical operation can become hundreds of physical gates and corrections.

That makes these compilers both complex and dangerous. A bug in an ordinary compiler crashes loudly. A bug here silently
changes what the program computes, and since quantum output is already noisy, you can't tell the corruption from ordinary
noise. You can't test it away either: the input space is astronomical, and measuring a quantum state to inspect it
destroys it. The only real option is to **prove** the compiler correct. The trouble is that proving a whole quantum
compiler correct scales terribly: today's verified tools stall at a handful of qubits, right where error correction needs
thousands.

## What's genuinely new

Building a correctness check into each compilation step is a known, powerful idea; it's how trustworthy _classical_
compilers are built. qstack stands on that foundation. The new and exciting part is what becomes possible once the pieces
are quantum and the boundaries are drawn the way qstack draws them:

### A verified compiler for _any_ error-correction code, by swapping a package

Normally you'd build and verify a separate compiler for each QEC code: one for the surface code, another for Steane, and
so on. qstack verifies the **framework once** and treats each code as a **plug-in package**. Swap the package, get a
verified compiler for a new code, with no re-proving.

This turns a vague question into a precise one: _what does a code's package actually have to provide?_ Nail down that
minimal interface, and you've also nailed down a clean, formal answer to something the field states only informally:
**what it even means for an error-correction scheme to be correct.**

### Stack the codes, and the guarantees stack too, for free

Error-correction codes combine. Layer a code that fixes one kind of error over a code that fixes another, and you get a
stronger code that fixes both. (Stacking the two simplest repetition codes literally rebuilds the famous Shor code;
stacking a code on itself doubles its strength.)

The payoff: in qstack, **verifying the pieces verifies the combination**. Prove two simple codes correct and the stronger
stacked code is correct _automatically_, with no new proof. Correctness composes exactly the way the codes themselves
compose. Build a library of verified building blocks, snap them together, and the trust assembles with them.

### It's not only for error correction: it's the _same_ machinery all the way down

The "swappable package" idea is broader than QEC. An ordinary compiler step that has nothing to do with error correction
(say, lowering logical gates to a specific machine's instruction set) is just a package whose code is **trivial**: one
physical qubit per logical qubit, no encoding to undo. The encode/decode it plugs in are the identity.

So the framework doesn't treat error correction as a special case grafted onto a normal compiler. A plain
hardware-lowering pass and a surface-code pass are the _same kind of object_, checked by the _same correctness
machinery_, differing only in how nontrivial their package is. One verification story covers the whole pipeline, from
high-level circuits down to the metal. Error correction is simply the rich end of a single spectrum.

## Why qstack can do this

Both ideas rest on one design choice: **keep classical computation out of the quantum part of the program.**

Most quantum representations tangle quantum operations together with classical variables, arithmetic, and branching.
qstack refuses to. The quantum program is a clean graph of purely quantum operations; everywhere classical logic is
needed (decoding a measurement, deciding what to do next), it lives behind an explicit **sealed box** the compiler treats
as opaque.

That single discipline is what unlocks everything else:

- **The pieces stay small and regular,** so each can be checked mechanically instead of by brute-force simulation.
- **The compiler never touches the sealed boxes.** The decoders and decision functions a user writes pass through
  compilation untouched, so trust splits cleanly: the compiler is _proven_ correct on the quantum side, and the sealed
  boxes are _trusted_ (or checked separately as ordinary classical code).
- **Stacking codes just stacks boundaries,** which is the reason combining verified pieces yields a verified whole for
  free.

qstack delivers this as three layers: a friendly surface language (`qstackqasm`, a trimmed subset of OpenQASM 3.0), a
clean intermediate representation (the qstack MLIR dialect), and the verification layer above. The per-operation
correctness checks build directly on the stabilizer/logical-action method of _Stabilizer Circuit Verification_
(Kliuchnikov, Beverland, Paetznick). qstack's contribution is the framework that makes those checks **reusable across
codes and compositional across layers**, not the checks themselves.

## The one-line version

> Other verified compilers prove _one_ compiler correct. qstack is a kit for assembling _verified compilers for
> error-corrected quantum programs_ out of reusable, composable, plug-in parts, so the trust scales with the system
> instead of being rebuilt for every code.
