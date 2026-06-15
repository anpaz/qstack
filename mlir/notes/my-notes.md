- need to implement the rep3phase compiler, then update the rep3_demo notebook to use this one.

- need a mechanism to provide the semantics of a dialect. right now the emulator is hardcoding all the operations.

- the set of gates is hardcoded in 'lowering', so the surface language has them hardcoded.

- we don't have a single BaseOpRewriter... it's only used for simple lowering.
  - related?: there are no handlers for core ops for rep3_trivial, just for dialects. so there is an `elif isinstance(op, MeasureOp):...` for each core op.

- README (combine with DESIGN and POSITIONING)
