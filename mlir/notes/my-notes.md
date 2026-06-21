- need to implement the rep3phase compiler, then update the rep3_demo notebook to use this one.

- we don't have a single BaseOpRewriter... it's only used for simple lowering.
  - related?: there are no handlers for core ops for rep3_trivial, just for dialects. so there is an `elif isinstance(op, MeasureOp):...` for each core op.

- we need a STIM based simulator.

- README (combine with DESIGN and POSITIONING)

- we need a better compiler error handling, not just throwing Exception on first error.
