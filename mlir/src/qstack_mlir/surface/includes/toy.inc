// qstack toy ISA — body-less gate declarations for the QSTACKQASM surface //
parser to consult before lowering gate-call statements. #pragma qstack.isa toy;
gate flip q; gate mix q; gate skew(bias) q; gate entangle c, t;
