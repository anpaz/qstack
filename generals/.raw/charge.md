# Charge.md

Your charge is to write a dissertation proposal in the area of representations, including compiler-intermediate representations, for quantum programs, including programs that have classical components for error correction or other purposes. Focus in particular on how the precise semantics for programs can enable proving that compiler transformations are meaning-preserving (i.e., correct).

We expect approximately half of your report to be a thorough review of prior results by others. Some of this work may be helpful to you while other work may be related in that it defines semantics and analyses for quantum programs but for problems such as circuit optimization that are not your focus. Throughout your report, make sure to cite papers just as you would in a research publication.

While you should include significantly more citations than the list here, be sure to include sufficient discussion of these papers or, if necessary, discuss with your committee in advance why they are not relevant to your proposal:

* Alexander S Green, Peter LeFanu Lumsdaine, Neil J Ross, Peter Selinger, and Benoît Valiron. . Quipper: A Scalable Quantum Programming Language. PLDI 2013.
* Mikhail Mints, Finn Voichick, Leonidas Lampropoulos, and Robert Rand. Compositional Quantum Control Flow with Efficient Compilation in Qunity. OOPSLA 2025.
* Benjamin Bichsel, Maximilian Baader, Timon Gehr, and Martin Vechev. Silq: A High-Level Quantum Language with Safe Uncomputation and Intuitive Semantics. PLDI 2020.
* Damian Rovara, Lukas Burgholzer, and Robert Wille. A Framework for Debugging Quantum Programs. 2025 IEEE International Conference on Quantum Software
* Nathaniel Tornow, Emmanouil Giortamis, and Pramod Bhatotia. QVM: Quantum Gate Virtualization Machine. PLDI 2025.
* Ali Javadi-Abhari, Matthew Treinish, Kevin Krsulich, Christopher J. Wood, Jake Lishman, Julien Gacon, Simon Martiel, Paul D. Nation, Lev S. Bishop, Andrew W. Cross, Blake R. Johnson, and Jay M. Gambetta. Quantum computing with Qiskit. https://arxiv.org/abs/2405.08810
* You should also consider the relevance of existing intermediate representations for quantum programs such as QIR (https://github.com/qir-alliance/qir-spec).


Include in your report the relevant work you have completed to date, but focus more on the upcoming work you are proposing and how the full body of work fits together to validate your claims. Identify what will demonstrate success, what the largest risks to success are likely to be, and what is novel.

In more detail, the proposal should consist of the following sections (or a reasonable refactoring thereof):

1. Introduction to the area and motivation for the problem(s) you propose to solve. Include a proposed set of hypotheses that the thesis will demonstrate, and a synopsis of the likely contributions of the work.
2. Related work including a discussion of how your proposed work either leverages that work (e.g., techniques you plan to adopt) or differs from it (e.g., novel contributions). For your Generals report, we recommend you focus primarily on extending your existing qstack work to show how compiler transformations can be (rigorously but manually) proved correct and how you can adapt your work to a compiler intermediate representation such as in MLIR.
3. A description of the work for your dissertation that you have already completed and the results you have collected. Describe the strengths and weaknesses of your approach to date, including what it can and cannot do (or in the case of results, what those results show and what are the limitations of your results).
4. A description of proposed work remaining for your dissertation. Describe the main challenges and innovations that are needed to accomplish the proposed hypotheses, with as much description as possible of how you will tackle each one.
5. Methodology and evaluation: how do you plan to evaluate whether your ideas work or your hypotheses are correct?
6. Conclusions and future work that will not be covered in the dissertation research.

Throughout, you may assume knowledge of both compilers and quantum computing – for any background on notation, semantics, or relevant linear algebra you may point to other resources. Notation specific to qstack and your approach should be explained so that your proposal is, to this extent, self-contained.

The committee is charged with evaluating whether you are prepared to proceed with writing your dissertation. In doing this evaluation, we will ask ourselves:

* Are the proposed hypotheses significant and novel?
* Are the proposed evaluation methods capable of demonstrating the hypotheses?
* Is the scope of work needed to complete the thesis plausible to be completed within roughly one year?
* What likelihood does the student have of completing a successful thesis -- has sufficient preliminary work been done to make technical and other risks manageable?
* Is the related work and the comparison to the proposed work accurately represented?
* Are the student's writing and presentation skills adequate to the rigors of completing a dissertation?