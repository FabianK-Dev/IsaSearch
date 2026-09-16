# Duplicate analysis: Near-exact matches

Generated at 2026\-09\-16T16:03:13.

The selected AFP entries are compared with the indexed AFP and Isabelle library. Matches within the source entry are excluded. The tiers guide human review; semantic or syntactic similarity does not establish logical duplication.

This report contains only **near-exact** candidates.

Source blocks are excerpts and may end mid-statement; follow the links for complete source.

Tiers:

- `near-exact`: distance ≤ 0.05 or syntactic similarity ≥ 0.9.

## Definitions

7 of 322 analysed definitions have matches in this report (14 candidate pairs).

Candidate tiers: 14 near-exact.

Full-run positive control: 321 of 322 documents retrieved themselves at a distance of about 0 (mean self distance 0.00025570429745492906).

Full-run synthetic control: 6 of 6 documents with a syntactically near-identical counterpart in another entry were recovered within the top 10 (recall 1.00).

Most frequent match locations in this report:

- [IMP\_With\_Speculation](<https://isa-afp.org/entries/IMP_With_Speculation.html>): 3 candidate pairs
- [Multitape\_To\_Singletape\_TM](<https://isa-afp.org/entries/Multitape_To_Singletape_TM.html>): 3 candidate pairs
- [Isabelle/src/HOL/Induct/Common\_Patterns\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-Induct/Common_Patterns.html>): 1 candidate pairs
- [Isabelle/src/HOL/IMP/Star\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Star.html>): 1 candidate pairs
- [HoareForDivergence](<https://isa-afp.org/entries/HoareForDivergence.html>): 1 candidate pairs
- [Isabelle/src/HOL/IMP/Small\_Step\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Small_Step.html>): 1 candidate pairs
- [IMP\_Noninterference\_Extension](<https://isa-afp.org/entries/IMP_Noninterference_Extension.html>): 1 candidate pairs
- [Isabelle/src/HOL/IMP/Types\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Types.html>): 1 candidate pairs
- [Isabelle/src/HOL/IMP/Def\_Init\_Small\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Def_Init_Small.html>): 1 candidate pairs
- [Abstract\_Consistency\_Property](<https://isa-afp.org/entries/Abstract_Consistency_Property.html>): 1 candidate pairs

### Laurent\_Annulus (2026\-08\-22)

0 of 9 definitions have at least one candidate in this report.

### Trace\_Based\_Rely\_Guarantee (2026\-08\-11)

3 of 62 definitions have at least one candidate in this report.

#### [Prelim\.star\|const](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Trace_Based_Rely_Guarantee/Prelim.thy#L366>) — near-exact

```isabelle
inductive
  star :: "('a ⇒ 'a ⇒ bool) ⇒ 'a ⇒ 'a ⇒ bool"
for r where
refl:  "star r x x" |
step:  "r x y ⟹ star r y z ⟹ star r x z"
```

- **near-exact** (inductive) [Common\_Patterns\.star\|const](<https://isabelle.in.tum.de/library/HOL/HOL-Induct/Common_Patterns.html>) in [Isabelle/src/HOL/Induct/Common\_Patterns\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-Induct/Common_Patterns.html>) (distance 0.0214, syntactic 0.75, verdict DUPLICATE)

    Both items define the transitive closure \(star\) of a binary relation using the same inductive rules: reflexivity and transitivity\.

    ```isabelle
    inductive star :: "('a ⇒ 'a ⇒ bool) ⇒ 'a ⇒ 'a ⇒ bool" for r
    where
      refl: "star r x x" for x
    | step: "star r x z" if "r x y" and "star r y z" for x y z
    ```

- **near-exact** (inductive) [Star\.star\|const](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Star.html>) in [Isabelle/src/HOL/IMP/Star\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Star.html>) (distance 0.0278, syntactic 1.00, verdict DUPLICATE)

    The two items are identical in their definition of the transitive closure \(star\) of a relation, using the same constructors and logic\.

    ```isabelle
    inductive
      star :: "('a ⇒ 'a ⇒ bool) ⇒ 'a ⇒ 'a ⇒ bool"
    for r where
    refl:  "star r x x" |
    step:  "r x y ⟹ star r y z ⟹ star r x z"
    ```

- **near-exact** (inductive) [Language\_Prelims\.star\|const](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/IMP_With_Speculation/IMP/Language_Prelims.thy#L225>) in [IMP\_With\_Speculation](<https://isa-afp.org/entries/IMP_With_Speculation.html>) (distance 0.0285, syntactic 1.00, verdict DUPLICATE)

    The two items are identical in their definition of the transitive closure \(star\) of a relation, using the same constructors and logic\.

    ```isabelle
    inductive
      star :: "('a ⇒ 'a ⇒ bool) ⇒ 'a ⇒ 'a ⇒ bool"
    for r where
    refl:  "star r x x" |
    step:  "r x y ⟹ star r y z ⟹ star r x z"
    ```

- **near-exact** (inductive) [MiscLemmas\.star\|const](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/HoareForDivergence/MiscLemmas.thy#L5>) in [HoareForDivergence](<https://isa-afp.org/entries/HoareForDivergence.html>) (distance 0.0291, syntactic 0.95)

    ```isabelle
    inductive star :: "('a ⇒ 'a ⇒ bool) ⇒ 'a ⇒ 'a ⇒ bool" for r where
      refl[simp,intro]: "star r x x"
    | step: "r x y ⟹ star r y z ⟹ star r x z"
    ```

- **near-exact** (inductive) [Language\_Prelims\.starn\|const](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/IMP_With_Speculation/IMP/Language_Prelims.thy#L256>) in [IMP\_With\_Speculation](<https://isa-afp.org/entries/IMP_With_Speculation.html>) (distance 0.1117, syntactic 0.92)

    ```isabelle
    inductive
      starn :: "('a ⇒ 'a ⇒ bool) ⇒ nat ⇒ 'a ⇒ 'a ⇒ bool"
    for r where
    refl:  "starn r 0 x x" |
    step:  "r x y ⟹ starn r n y z ⟹ starn r (Suc n)x z"
    ```

#### [Prelim\.final\|const](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Trace_Based_Rely_Guarantee/Prelim.thy#L392>) — near-exact

```isabelle
definition "final r x ≡ ∀y. ¬ r x y"
```

- **near-exact** (definition) [Language\_Prelims\.final\|const](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/IMP_With_Speculation/IMP/Language_Prelims.thy#L323>) in [IMP\_With\_Speculation](<https://isa-afp.org/entries/IMP_With_Speculation.html>) (distance 0.0002, syntactic 1.00, verdict DUPLICATE)

    Both items are identical definitions of the same mathematical concept\.

    ```isabelle
    definition "final r x ≡ ∀y. ¬ r x y"
    ```

#### [Prelim\.Step\.small\_steps\|const](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Trace_Based_Rely_Guarantee/Prelim.thy#L414>) — near-exact

```isabelle
abbreviation
  small_steps :: "'com × 'state ⇒ 'com × 'state ⇒ bool" (infix "→*" 55)
  where "x →* y == star small_step x y"
```

- **near-exact** (abbreviation) [Small\_Step\.small\_steps\|const](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Small_Step.html>) in [Isabelle/src/HOL/IMP/Small\_Step\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Small_Step.html>) (distance 0.0177, syntactic 0.94, verdict DUPLICATE)

    Both items define the same abbreviation for the transitive closure of a small\-step relation using the same underlying function and infix notation\.

    ```isabelle
    abbreviation
      small_steps :: "com * state ⇒ com * state ⇒ bool" (infix ‹→*› 55)
    where "x →* y == star small_step x y"
    ```

- **near-exact** (abbreviation) [Small\_Step\.small\_steps\|const](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/IMP_Noninterference_Extension/Small_Step.thy#L234>) in [IMP\_Noninterference\_Extension](<https://isa-afp.org/entries/IMP_Noninterference_Extension.html>) (distance 0.0366, syntactic 0.87, verdict DUPLICATE)

    Both items define the same abbreviation for the reflexive transitive closure of a small\-step relation, differing only in the names of the state type and the notation used for the infix operator\.

    ```isabelle
    abbreviation small_steps :: "com × stage ⇒ com × stage ⇒ bool"
      (infix ‹→*› 55) where
    "cf →* cf' ≡ star small_step cf cf'"
    ```

- **near-exact** (abbreviation) [Types\.small\_steps\|const](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Types.html>) in [Isabelle/src/HOL/IMP/Types\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Types.html>) (distance 0.0458, syntactic 0.94, verdict DUPLICATE)

    Both items define the same abbreviation for the transitive closure of the small\_step relation using the same underlying 'star' function and notation\.

    ```isabelle
    abbreviation small_steps :: "com * state ⇒ com * state ⇒ bool" (infix ‹→*› 55)
    where "x →* y == star small_step x y"
    ```

- **near-exact** (abbreviation) [Def\_Init\_Small\.small\_steps\|const](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Def_Init_Small.html>) in [Isabelle/src/HOL/IMP/Def\_Init\_Small\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Def_Init_Small.html>) (distance 0.0517, syntactic 0.94)

    ```isabelle
    abbreviation small_steps :: "com * state ⇒ com * state ⇒ bool" (infix ‹→*› 55)
    where "x →* y == star small_step x y"
    ```

### Miquel (2026\-08\-11)

0 of 1 definitions have at least one candidate in this report.

### HOL\_in\_HOL\_Deep (2026\-08\-05)

0 of 93 definitions have at least one candidate in this report.

### Simson (2026\-08\-03)

0 of 7 definitions have at least one candidate in this report.

### Q0\_Completeness (2026\-08\-03)

1 of 31 definitions have at least one candidate in this report.

#### [Consistency\_Property\.Kinds\|const](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Q0_Completeness/Consistency_Property.thy#L247>) — near-exact

```isabelle
abbreviation Kinds :: ‹(nat, form) kind list› where
  ‹Kinds ≡ [C.kind, A.kind, B.kind, G.kind, D.kind]›
```

- **near-exact** (abbreviation) [Example\_Bounded\_FOL\.Kinds\|const](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Abstract_Consistency_Property/Example_Bounded_FOL.thy#L238>) in [Abstract\_Consistency\_Property](<https://isa-afp.org/entries/Abstract_Consistency_Property.html>) (distance 0.1372, syntactic 0.91, verdict VARIANT)

    Item A uses specific types \`nat\` and \`form\` for the list elements, whereas Item B uses polymorphic type variables \`'f\` and \`'p\`, making Item B a generalization of Item A\.

    ```isabelle
    abbreviation Kinds :: ‹('f, ('f, 'p) fm) kind list› where
      ‹Kinds ≡ [C.kind, A.kind, B.kind, G.kind, D.kind]›
    ```

### Dinitz\_Garg\_Goemans\_Counterexample (2026\-07\-22)

0 of 30 definitions have at least one candidate in this report.

### Jacobian\_Counterexample (2026\-07\-20)

0 of 33 definitions have at least one candidate in this report.

### Right\_Forward\_Closures (2026\-07\-17)

0 of 11 definitions have at least one candidate in this report.

### Multitape\_TM\_Substrate (2026\-07\-14)

3 of 45 definitions have at least one candidate in this report.

#### [Multitape\_Substrate\_Core\.dir\|type](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_TM_Substrate/Multitape_Substrate_Core.thy#L42>) — near-exact

```isabelle
datatype dir = R | L | N
```

- **near-exact** (datatype) [TM\_Common\.dir\|type](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_To_Singletape_TM/TM_Common.thy#L9>) in [Multitape\_To\_Singletape\_TM](<https://isa-afp.org/entries/Multitape_To_Singletape_TM.html>) (distance 0.0003, syntactic 1.00, verdict DUPLICATE)

    Both items define the exact same datatype 'dir' with the same constructors R, L, and N\.

    ```isabelle
    datatype dir = R | L | N
    ```

#### [Multitape\_Substrate\_Core\.go\_dir\|const](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_TM_Substrate/Multitape_Substrate_Core.thy#L44>) — near-exact

```isabelle
fun go_dir :: "dir ⇒ nat ⇒ nat" where
  "go_dir R n = Suc n"
| "go_dir L n = n - 1"
| "go_dir N n = n"
```

- **near-exact** (fun) [TM\_Common\.go\_dir\|const](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_To_Singletape_TM/TM_Common.thy#L11>) in [Multitape\_To\_Singletape\_TM](<https://isa-afp.org/entries/Multitape_To_Singletape_TM.html>) (distance 0.0811, syntactic 1.00, verdict DUPLICATE)

    The two definitions are identical in their mathematical content and structure, differing only in minor formatting/whitespace\.

    ```isabelle
    fun go_dir :: "dir ⇒ nat ⇒ nat" where
      "go_dir R n = Suc n" 
    | "go_dir L n = n - 1" 
    | "go_dir N n = n"
    ```

#### [Multitape\_Substrate\_Core\.mttm\|type](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_TM_Substrate/Multitape_Substrate_Core.thy#L63>) — near-exact

```isabelle
datatype ('q, 'a) mttm = MTTM
  (Q_tm: "'q set")        ― ‹Q — states›
  "'a set"                ― ‹‹Σ› — input alphabet›
  (Γ_tm: "'a set")        ― ‹‹Γ› — tape alphabet›
  'a                      ― ‹blank›
  'a                      ― ‹left endmarker›
  "('q × (nat ⇒ 'a) × 'q × (nat ⇒ 'a) × (nat ⇒ dir)) set"
                          ― ‹transitions ‹δ››
  'q                      ― ‹start state›
  'q                      ― ‹accept state›
  'q                      ― ‹reject state›
  nat                     ― ‹‹k› — tape count›
```

- **near-exact** (datatype) [Multitape\_TM\.mttm\|type](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_To_Singletape_TM/Multitape_TM.thy#L17>) in [Multitape\_To\_Singletape\_TM](<https://isa-afp.org/entries/Multitape_To_Singletape_TM.html>) (distance 0.0494, syntactic 0.53, verdict VARIANT)

    Item A defines a multi\-tape Turing machine where the tape length is fixed to a specific natural number 'k', whereas Item B generalizes this by parameterizing the tape length as a type variable 'k'\.

    ```isabelle
    datatype ('q,'a,'k)mttm = MTTM 
      (Q_tm: "'q set")   (* Q - states *)
      "'a set"   (* Sigma - input alphabet *)
      (Γ_tm: "'a set")   (* Gamma - tape alphabet *)
      'a         (* blank *)
      'a         (* left endmarker *)
      "('q × ('k ⇒ 'a) × 'q × ('k ⇒ 'a) × ('k ⇒ dir)) set" (* transitions δ *)
      'q         (* start state *)
      'q         (* accept state *)
      'q
    ```

## Theorems

30 of 1160 analysed theorems have matches in this report (53 candidate pairs).

Candidate tiers: 53 near-exact.

Full-run positive control: 1160 of 1160 documents retrieved themselves at a distance of about 0 (mean self distance 0.0002550172908552762).

Most frequent match locations in this report:

- [Perrons\_Formula](<https://isa-afp.org/entries/Perrons_Formula.html>): 6 candidate pairs
- [Isabelle/src/HOL/Complex\_Analysis/Contour\_Integration\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-Complex_Analysis/Contour_Integration.html>): 5 candidate pairs
- [IMP\_With\_Speculation](<https://isa-afp.org/entries/IMP_With_Speculation.html>): 3 candidate pairs
- [Q0\_Metatheory](<https://isa-afp.org/entries/Q0_Metatheory.html>): 3 candidate pairs
- [First\_Order\_Rewriting](<https://isa-afp.org/entries/First_Order_Rewriting.html>): 3 candidate pairs
- [Multitape\_To\_Singletape\_TM](<https://isa-afp.org/entries/Multitape_To_Singletape_TM.html>): 3 candidate pairs
- [Multitape\_Alphabet\_Enlargement](<https://isa-afp.org/entries/Multitape_Alphabet_Enlargement.html>): 3 candidate pairs
- [Isabelle/src/HOL/IMP/Star\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Star.html>): 2 candidate pairs
- [Regular\_Tree\_Relations](<https://isa-afp.org/entries/Regular_Tree_Relations.html>): 2 candidate pairs
- [Query\_Optimization](<https://isa-afp.org/entries/Query_Optimization.html>): 2 candidate pairs
- [Complex\_Geometry](<https://isa-afp.org/entries/Complex_Geometry.html>): 2 candidate pairs
- [Abstract\_Consistency\_Property](<https://isa-afp.org/entries/Abstract_Consistency_Property.html>): 2 candidate pairs
- [Detour\_Calculus](<https://isa-afp.org/entries/Detour_Calculus.html>): 1 candidate pairs
- [Isabelle/src/HOL/Analysis/Uniform\_Limit\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-Analysis/Uniform_Limit.html>): 1 candidate pairs
- [Arithmetic\_Geometric\_Mean](<https://isa-afp.org/entries/Arithmetic_Geometric_Mean.html>): 1 candidate pairs
- [Isabelle/src/HOL/Analysis/Summation\_Tests\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-Analysis/Summation_Tests.html>): 1 candidate pairs
- [Path\_Automation](<https://isa-afp.org/entries/Path_Automation.html>): 1 candidate pairs
- [Isabelle/src/HOL/Induct/Common\_Patterns\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-Induct/Common_Patterns.html>): 1 candidate pairs
- [Z\_Toolkit](<https://isa-afp.org/entries/Z_Toolkit.html>): 1 candidate pairs
- [List\-Infinite](<https://isa-afp.org/entries/List-Infinite.html>): 1 candidate pairs

### Laurent\_Annulus (2026\-08\-22)

7 of 50 theorems have at least one candidate in this report.

#### [Laurent\_Annulus\.contour\_integral\_rmul\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Laurent_Annulus/Laurent_Annulus.thy#L86>) — near-exact

```isabelle
lemma contour_integral_rmul: "contour_integral g (λx. f x * c) = contour_integral g f * c"
proof (cases "c = 0")
  case [simp]: False
  show ?thesis
  proof (cases "f contour_integrable_on g")
    case True
    thus ?thesis
      by (simp add: contour_integral_unique has_contour_integral_integral has_contour_integral_rmul)
  next
    case False
    thus ?thesis
      using contour_integrable_rmul_iff not_integrable_contour_integral by force
  qed
qed auto
```

- **near-exact** (theorems) [Perron\_Prerequisites\.contour\_integral\_rmul\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Perrons_Formula/Perron_Prerequisites.thy#L447>) in [Perrons\_Formula](<https://isa-afp.org/entries/Perrons_Formula.html>) (distance 0.0003, syntactic 1.00, verdict DUPLICATE)

    Item A and Item B are identical in their mathematical content and notation\.

    ```isabelle
    lemma contour_integral_rmul: "contour_integral g (λx. f x * c) = contour_integral g f * c"
    proof (cases "c = 0")
      case [simp]: False
      show ?thesis
      proof (cases "f contour_integrable_on g")
        case True
        thus ?thesis
          by (simp add: contour_integral_unique has_contour_integral_integral has_contour_integral_rmul)
      next
        case False
        thus ?thesis
          using contour_integrable_rmul_iff not_integrable_contour_integral by force
      qed
    qed auto
    ```

- **near-exact** (theorems) [Contour\_Integration\.contour\_integral\_rmul\|thm](<https://isabelle.in.tum.de/library/HOL/HOL-Complex_Analysis/Contour_Integration.html>) in [Isabelle/src/HOL/Complex\_Analysis/Contour\_Integration\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-Complex_Analysis/Contour_Integration.html>) (distance 0.0387, syntactic 0.49, verdict VARIANT)

    Item A is a simplified version of the identity, while Item B is the formal statement including the necessary precondition for the existence/uniqueness of the integral\.

    ```isabelle
    lemma contour_integral_rmul:
      shows "f contour_integrable_on g
            ⟹ contour_integral g (λx. f x * c) = contour_integral g f * c"
      by (simp add: contour_integral_unique has_contour_integral_integral has_contour_integral_rmul)
    ```

- **near-exact** (theorems) [Contour\_Integration\.contour\_integral\_lmul\|thm](<https://isabelle.in.tum.de/library/HOL/HOL-Complex_Analysis/Contour_Integration.html>) in [Isabelle/src/HOL/Complex\_Analysis/Contour\_Integration\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-Complex_Analysis/Contour_Integration.html>) (distance 0.0429, syntactic 0.44, verdict VARIANT)

    Item A states the linearity of the contour integral with respect to scalar multiplication \(right\-multiplication\), while Item B is a more formal version that includes a precondition for integrability and addresses left\-multiplication\.

    ```isabelle
    lemma contour_integral_lmul:
      shows "f contour_integrable_on g
               ⟹ contour_integral g (λx. c * f x) = c*contour_integral g f"
      by (simp add: contour_integral_unique has_contour_integral_integral has_contour_integral_lmul)
    ```

- **near-exact** (theorems) [Perron\_Prerequisites\.contour\_integral\_lmul\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Perrons_Formula/Perron_Prerequisites.thy#L462>) in [Perrons\_Formula](<https://isa-afp.org/entries/Perrons_Formula.html>) (distance 0.0447, syntactic 0.61)

    ```isabelle
    lemma contour_integral_lmul: "contour_integral g (λx. c * f x) = c * contour_integral g f"
      by (subst (1 2) mult.commute) (rule contour_integral_rmul)
    ```

#### [Laurent\_Annulus\.contour\_integral\_lmul\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Laurent_Annulus/Laurent_Annulus.thy#L101>) — near-exact

```isabelle
lemma contour_integral_lmul: "contour_integral g (λx. c * f x) = c * contour_integral g f"
  by (subst (1 2) mult.commute) (rule contour_integral_rmul)
```

- **near-exact** (theorems) [Perron\_Prerequisites\.contour\_integral\_lmul\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Perrons_Formula/Perron_Prerequisites.thy#L462>) in [Perrons\_Formula](<https://isa-afp.org/entries/Perrons_Formula.html>) (distance 0.0003, syntactic 1.00, verdict DUPLICATE)

    Item A and Item B are identical in their mathematical content, notation, and formal structure\.

    ```isabelle
    lemma contour_integral_lmul: "contour_integral g (λx. c * f x) = c * contour_integral g f"
      by (subst (1 2) mult.commute) (rule contour_integral_rmul)
    ```

- **near-exact** (theorems) [Contour\_Integration\.contour\_integral\_lmul\|thm](<https://isabelle.in.tum.de/library/HOL/HOL-Complex_Analysis/Contour_Integration.html>) in [Isabelle/src/HOL/Complex\_Analysis/Contour\_Integration\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-Complex_Analysis/Contour_Integration.html>) (distance 0.0262, syntactic 0.58, verdict VARIANT)

    Item A is a simplified version of the identity, while Item B is a more formal statement that includes the necessary precondition of integrability\.

    ```isabelle
    lemma contour_integral_lmul:
      shows "f contour_integrable_on g
               ⟹ contour_integral g (λx. c * f x) = c*contour_integral g f"
      by (simp add: contour_integral_unique has_contour_integral_integral has_contour_integral_lmul)
    ```

- **near-exact** (theorems) [Contour\_Integration\.contour\_integral\_rmul\|thm](<https://isabelle.in.tum.de/library/HOL/HOL-Complex_Analysis/Contour_Integration.html>) in [Isabelle/src/HOL/Complex\_Analysis/Contour\_Integration\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-Complex_Analysis/Contour_Integration.html>) (distance 0.0317, syntactic 0.59, verdict VARIANT)

    Item A states the linearity of the contour integral with respect to a scalar constant on the left side of the integrand, while Item B states it for a constant on the right side; they are different formulations of the same property\.

    ```isabelle
    lemma contour_integral_rmul:
      shows "f contour_integrable_on g
            ⟹ contour_integral g (λx. f x * c) = contour_integral g f * c"
      by (simp add: contour_integral_unique has_contour_integral_integral has_contour_integral_rmul)
    ```

- **near-exact** (theorems) [Perron\_Prerequisites\.contour\_integral\_rmul\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Perrons_Formula/Perron_Prerequisites.thy#L447>) in [Perrons\_Formula](<https://isa-afp.org/entries/Perrons_Formula.html>) (distance 0.0460, syntactic 0.61)

    ```isabelle
    lemma contour_integral_rmul: "contour_integral g (λx. f x * c) = contour_integral g f * c"
    proof (cases "c = 0")
      case [simp]: False
      show ?thesis
      proof (cases "f contour_integrable_on g")
        case True
        thus ?thesis
          by (simp add: contour_integral_unique has_contour_integral_integral has_contour_integral_rmul)
      next
        case False
        thus ?thesis
          using contour_integrable_rmul_iff not_integrable_contour_integral by force
      qed
    qed auto
    ```

#### [Laurent\_Annulus\.contour\_integral\_divide\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Laurent_Annulus/Laurent_Annulus.thy#L104>) — near-exact

```isabelle
lemma contour_integral_divide: "contour_integral g (λx. f x / c) = contour_integral g f / c"
  using contour_integral_rmul[of g f "inverse c"] by (simp add: field_simps)
```

- **near-exact** (theorems) [Perron\_Prerequisites\.contour\_integral\_divide\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Perrons_Formula/Perron_Prerequisites.thy#L465>) in [Perrons\_Formula](<https://isa-afp.org/entries/Perrons_Formula.html>) (distance 0.0143, syntactic 1.00, verdict DUPLICATE)

    Item A and Item B are identical in their mathematical content, notation, and formal structure\.

    ```isabelle
    lemma contour_integral_divide: "contour_integral g (λx. f x / c) = contour_integral g f / c"
      using contour_integral_rmul[of g f "inverse c"] by (simp add: field_simps)
    ```

- **near-exact** (theorems) [Contour\_Integration\.contour\_integral\_div\|thm](<https://isabelle.in.tum.de/library/HOL/HOL-Complex_Analysis/Contour_Integration.html>) in [Isabelle/src/HOL/Complex\_Analysis/Contour\_Integration\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-Complex_Analysis/Contour_Integration.html>) (distance 0.0381, syntactic 0.54, verdict VARIANT)

    Item A is a specific instance or a simplified version of the property, while Item B is a more formal statement that includes the necessary precondition of integrability to ensure the equality is well\-defined\.

    ```isabelle
    lemma contour_integral_div:
      shows "f contour_integrable_on g
            ⟹ contour_integral g (λx. f x / c) = contour_integral g f / c"
      by (simp add: contour_integral_unique has_contour_integral_integral has_contour_integral_div)
    ```

#### [Laurent\_Annulus\.contour\_integral\_affine\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Laurent_Annulus/Laurent_Annulus.thy#L14>) — near-exact

```isabelle
lemma contour_integral_affine:
  assumes "valid_path γ" "c ≠ 0"
  shows "contour_integral ((λx. c * x + b) ∘ γ) f = contour_integral γ (λw. c * f (c * w + b))"
proof -
  define ff where "ff=(λx. c*x+b)"
  have "contour_integral (ff ∘ γ) f = contour_integral γ (λw. deriv ff w * f (ff w))"
  proof (rule contour_integral_comp_analyticW)
    show "ff analytic_on UNIV" "path_image γ ⊆ UNIV" "valid_path γ"
    unfolding ff_def using ‹valid_path γ›
    by (auto intro: analytic_intros)
  qed
  also have "… = contour_integral γ (λw. c * f (c * w + b))"
  proof -
    have "deriv ff  x = c" "ff x = c*x+b
```

- **near-exact** (theorems) [Detour\_Prerequisites\.contour\_integral\_affine\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Detour_Calculus/Detour_Prerequisites.thy#L151>) in [Detour\_Calculus](<https://isa-afp.org/entries/Detour_Calculus.html>) (distance 0.0194, syntactic 1.00, verdict DUPLICATE)

    Item A and Item B are identical in their assumptions and conclusions, stating the same mathematical identity for the contour integral of an affine transformation\.

    ```isabelle
    lemma contour_integral_affine:
      assumes "valid_path γ" "c ≠ 0"
      shows "contour_integral ((λx. c * x + b) ∘ γ) f = contour_integral γ (λw. c * f (c * w + b))"
    proof -
      define ff where "ff=(λx. c*x+b)"
      have "contour_integral (ff ∘ γ) f = contour_integral γ (λw. deriv ff w * f (ff w))"
      proof (rule contour_integral_comp_analyticW)
        show "ff analytic_on UNIV" "path_image γ ⊆ UNIV" "valid_path γ"
        unfolding ff_def using ‹valid_path γ›
        by (auto intro: analytic_intros)
      qed
      also have "… = contour_integral γ (λw. c * f (c * w + b))"
      proof -
        have "deriv ff  x = c" "ff x = c*x+b
    ```

#### [Laurent\_Annulus\.uniform\_limit\_compose'\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Laurent_Annulus/Laurent_Annulus.thy#L107>) — near-exact

```isabelle
lemma uniform_limit_compose':
  assumes "uniform_limit A f g F" and "h ` B ⊆ A"
  shows   "uniform_limit B (λn x. f n (h x)) (λx. g (h x)) F"
  unfolding uniform_limit_iff
proof safe
  fix e :: real
  assume e: "e > 0"
  from e and assms(1) have "∀⇩F n in F. ∀x∈A. dist (f n x) (g x) < e"
    by (auto simp: uniform_limit_iff)
  thus "∀⇩F n in F. ∀x∈B. dist (f n (h x)) (g (h x)) < e"
    by eventually_elim (use assms(2) in blast)
qed
```

- **near-exact** (theorems) [Uniform\_Limit\.uniform\_limit\_compose'\|thm](<https://isabelle.in.tum.de/library/HOL/HOL-Analysis/Uniform_Limit.html>) in [Isabelle/src/HOL/Analysis/Uniform\_Limit\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-Analysis/Uniform_Limit.html>) (distance 0.0198, syntactic 0.98, verdict DUPLICATE)

    Both lemmas state the same mathematical fact regarding the composition of uniformly convergent sequences of functions, where the only difference is the notation used for the subset relation \(\`\`h \` B ⊆ A\`\` vs \`\`h ∈ B → A\`\`\)\.

    ```isabelle
    lemma uniform_limit_compose':
      assumes "uniform_limit A f g F" and "h ∈ B → A"
      shows   "uniform_limit B (λn x. f n (h x)) (λx. g (h x)) F"
      unfolding uniform_limit_iff
    proof (intro strip)
      fix e :: real
      assume e: "e > 0"
      with assms(1) have "∀⇩F n in F. ∀x∈A. dist (f n x) (g x) < e"
        by (auto simp: uniform_limit_iff)
      thus "∀⇩F n in F. ∀x∈B. dist (f n (h x)) (g (h x)) < e"
        by eventually_elim (use assms(2) in blast)
    qed
    ```

- **near-exact** (theorems) [Perron\_Prerequisites\.uniform\_limit\_compose'\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Perrons_Formula/Perron_Prerequisites.thy#L122>) in [Perrons\_Formula](<https://isa-afp.org/entries/Perrons_Formula.html>) (distance 0.0213, syntactic 1.00, verdict DUPLICATE)

    The two items are identical in their assumptions, conclusions, and unfolding instructions\.

    ```isabelle
    lemma uniform_limit_compose':
      assumes "uniform_limit A f g F" and "h ` B ⊆ A"
      shows   "uniform_limit B (λn x. f n (h x)) (λx. g (h x)) F"
      unfolding uniform_limit_iff
    proof safe
      fix e :: real
      assume e: "e > 0"
      from e and assms(1) have "∀⇩F n in F. ∀x∈A. dist (f n x) (g x) < e"
        by (auto simp: uniform_limit_iff)
      thus "∀⇩F n in F. ∀x∈B. dist (f n (h x)) (g (h x)) < e"
        by eventually_elim (use assms(2) in blast)
    qed
    ```

- **near-exact** (theorems) [AGM\_Lemma\_Bucket\.uniform\_limit\_compose'\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Arithmetic_Geometric_Mean/AGM_Lemma_Bucket.thy#L48>) in [Arithmetic\_Geometric\_Mean](<https://isa-afp.org/entries/Arithmetic_Geometric_Mean.html>) (distance 0.0258, syntactic 1.00, verdict DUPLICATE)

    The two items are identical in their assumptions, conclusions, and unfolding instructions\.

    ```isabelle
    lemma uniform_limit_compose':
      assumes "uniform_limit A f g F" and "h ` B ⊆ A"
      shows   "uniform_limit B (λn x. f n (h x)) (λx. g (h x)) F"
      unfolding uniform_limit_iff
    proof safe
      fix e :: real
      assume e: "e > 0"
      from e and assms(1) have "∀⇩F n in F. ∀x∈A. dist (f n x) (g x) < e"
        by (auto simp: uniform_limit_iff)
      thus "∀⇩F n in F. ∀x∈B. dist (f n (h x)) (g (h x)) < e"
        by eventually_elim (use assms(2) in blast)
    qed
    ```

#### [Laurent\_Annulus\.conv\_radius\_geI\_ex''\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Laurent_Annulus/Laurent_Annulus.thy#L198>) — near-exact

```isabelle
lemma conv_radius_geI_ex'':
  fixes f :: "nat ⇒ 'a :: {banach, real_normed_div_algebra}"
  assumes "⋀r. c < r ⟹ ereal r < R ⟹ summable (λn. f n * of_real r ^ n)"
  assumes "ereal c < R"
  shows   "conv_radius f ≥ R"
proof (rule ccontr)
  assume "¬R ≤ conv_radius f"
  hence "conv_radius f < R"
    by simp
  hence "max (conv_radius f) c < R"
    using assms(2) by simp
  then obtain x where "max (conv_radius f) c < ereal x" "x < R"
    by (meson ereal_dense2 less_max_iff_disj)
  hence x: "conv_radius f < ereal x" "c < x" "x < R"
    by simp_all
  have "conv_radius f ≥ 0"
    by (simp add: conv_ra
```

- **near-exact** (theorems) [Summation\_Tests\.conv\_radius\_geI\_ex'\|thm](<https://isabelle.in.tum.de/library/HOL/HOL-Analysis/Summation_Tests.html>) in [Isabelle/src/HOL/Analysis/Summation\_Tests\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-Analysis/Summation_Tests.html>) (distance 0.0617, syntactic 0.92, verdict VARIANT)

    Item A assumes a lower bound $c$ for the radius $r$ \(where $c$ is related to $R$\), whereas Item B assumes $r &gt; 0$; Item A is a more general version of the statement regarding the radius of convergence\.

    ```isabelle
    lemma conv_radius_geI_ex':
      fixes f :: "nat ⇒ 'a :: {banach, real_normed_div_algebra}"
      assumes "⋀r. 0 < r ⟹ ereal r < R ⟹ summable (λn. f n * of_real r^n)"
      shows   "conv_radius f ≥ R"
    proof (rule conv_radius_geI_ex)
      fix r assume "0 < r" "ereal r < R"
      with assms[of r] show "∃z. norm z = r ∧ summable (λn. f n * z ^ n)"
        by (intro exI[of _ "of_real r :: 'a"]) auto
    qed
    ```

#### [Laurent\_Annulus\.eq\_loops\_imp\_contour\_integral\_eq\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Laurent_Annulus/Laurent_Annulus.thy#L225>) — near-exact

```isabelle
lemma eq_loops_imp_contour_integral_eq:
  assumes "eq_loops p q" "valid_path p" "valid_path q"
  assumes "f analytic_on (path_image p ∩ path_image q)"
  shows   "contour_integral p f = contour_integral q f"
proof -
  from assms(4) obtain A where A: "open A" "f holomorphic_on A" "path_image p ∩ path_image q ⊆ A"
    using analytic_on_holomorphic by auto
  show ?thesis
  proof (rule Cauchy_theorem_homotopic_loops)
    show "homotopic_loops A p q"
      by (intro eq_loops_imp_homotopic assms A)
  qed (use assms A in auto)
qed
```

- **near-exact** (theorems) [Path\_Equivalence\.eq\_paths\_imp\_contour\_integral\_eq\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Path_Automation/Path_Equivalence.thy#L496>) in [Path\_Automation](<https://isa-afp.org/entries/Path_Automation.html>) (distance 0.0708, syntactic 0.98, verdict VARIANT)

    The two lemmas state the same conclusion \(equality of contour integrals\) under slightly different assumptions regarding the relationship between paths $p$ and $q$ \(being "loops" versus being "paths" that are equal\)\.

    ```isabelle
    lemma eq_paths_imp_contour_integral_eq:
      assumes "eq_paths p q" "valid_path p" "valid_path q"
      assumes "f analytic_on (path_image p ∩ path_image q)"
      shows   "contour_integral p f = contour_integral q f"
    proof -
      from assms(4) obtain A where A: "open A" "f holomorphic_on A" "path_image p ∩ path_image q ⊆ A"
        using analytic_on_holomorphic by auto
      show ?thesis
      proof (rule Cauchy_theorem_homotopic_paths)
        show "homotopic_paths A p q"
          by (intro eq_paths_imp_homotopic assms A)
      qed (use assms A in auto)
    qed
    ```

### Trace\_Based\_Rely\_Guarantee (2026\-08\-11)

3 of 325 theorems have at least one candidate in this report.

#### [Prelim\.star\_trans\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Trace_Based_Rely_Guarantee/Prelim.thy#L374>) — near-exact

```isabelle
lemma star_trans:
  "star r x y ⟹ star r y z ⟹ star r x z"
proof(induction rule: star.induct)
  case refl thus ?case .
next
  case step thus ?case by (metis star.step)
qed
```

- **near-exact** (theorems) [Language\_Prelims\.star\_trans\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/IMP_With_Speculation/IMP/Language_Prelims.thy#L233>) in [IMP\_With\_Speculation](<https://isa-afp.org/entries/IMP_With_Speculation.html>) (distance 0.0176, syntactic 1.00, verdict DUPLICATE)

    The two items are identical in their mathematical content and notation\.

    ```isabelle
    lemma star_trans:
      "star r x y ⟹ star r y z ⟹ star r x z"
    proof(induction rule: star.induct)
      case refl thus ?case .
    next
      case step thus ?case by (metis star.step)
    qed
    ```

- **near-exact** (theorems) [Star\.star\_trans\|thm](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Star.html>) in [Isabelle/src/HOL/IMP/Star\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Star.html>) (distance 0.0176, syntactic 1.00, verdict DUPLICATE)

    The two items are identical in their mathematical content and notation\.

    ```isabelle
    lemma star_trans:
      "star r x y ⟹ star r y z ⟹ star r x z"
    proof(induction rule: star.induct)
      case refl thus ?case .
    next
      case step thus ?case by (metis star.step)
    qed
    ```

- **near-exact** (theorems) [ISABELLE\_HOME/src/HOL/Induct/Common\_Patterns\.thy\|10348\.\.10641](<https://isabelle.in.tum.de/library/HOL/HOL-Induct/Common_Patterns.html>) in [Isabelle/src/HOL/Induct/Common\_Patterns\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-Induct/Common_Patterns.html>) (distance 0.0355, syntactic 1.00, verdict DUPLICATE)

    Both items state the exact same mathematical fact \(the transitivity of the reflexive transitive closure \`star\`\), differing only in the presence of a formal name for the lemma in Item A\.

    ```isabelle
    lemma "star r x y ⟹ star r y z ⟹ star r x z"
    proof (induct rule: star_induct) print_cases
      case base
      then show ?case .
    next
      case (step a b c) print_facts
      from step.prems have "star r b z" by (rule step.IH)
      with step.r show ?case by (rule star.step)
    qed
    ```

#### [Prelim\.star\_step1\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Trace_Based_Rely_Guarantee/Prelim.thy#L389>) — near-exact

```isabelle
lemma star_step1[simp, intro]: "r x y ⟹ star r x y"
  by(metis star.refl star.step)
```

- **near-exact** (theorems) [Language\_Prelims\.star\_step1\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/IMP_With_Speculation/IMP/Language_Prelims.thy#L249>) in [IMP\_With\_Speculation](<https://isa-afp.org/entries/IMP_With_Speculation.html>) (distance 0.0607, syntactic 1.00, verdict DUPLICATE)

    The two items are identical in mathematical content and syntax, differing only in formatting \(the placement of the 'by' keyword\)\.

    ```isabelle
    lemma star_step1[simp, intro]: "r x y ⟹ star r x y"
    by(metis star.refl star.step)
    ```

- **near-exact** (theorems) [Star\.star\_step1\|thm](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Star.html>) in [Isabelle/src/HOL/IMP/Star\.thy](<https://isabelle.in.tum.de/library/HOL/HOL-IMP/Star.html>) (distance 0.0896, syntactic 1.00, verdict DUPLICATE)

    The two items are identical in mathematical content and syntax, differing only in formatting \(the placement of the 'by' keyword\)\.

    ```isabelle
    lemma star_step1[simp, intro]: "r x y ⟹ star r x y"
    by(metis star.refl star.step)
    ```

#### [Prelim\.final\_star\_eq\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Trace_Based_Rely_Guarantee/Prelim.thy#L394>) — near-exact

```isabelle
lemma final_star_eq: "final r x ⟹ star r x y ⟹ x = y"
by (metis final_def star.cases)
```

- **near-exact** (theorems) [Language\_Prelims\.final\_star\_eq\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/IMP_With_Speculation/IMP/Language_Prelims.thy#L325>) in [IMP\_With\_Speculation](<https://isa-afp.org/entries/IMP_With_Speculation.html>) (distance 0.0771, syntactic 1.00, verdict DUPLICATE)

    Item A and Item B are identical in their mathematical content, notation, and structure\.

    ```isabelle
    lemma final_star_eq: "final r x ⟹ star r x y ⟹ x = y"
    by (metis final_def star.cases)
    ```

### Miquel (2026\-08\-11)

0 of 10 theorems have at least one candidate in this report.

### HOL\_in\_HOL\_Deep (2026\-08\-05)

3 of 273 theorems have at least one candidate in this report.

#### [Calculus\.infinite\_inj\_image\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/HOL_in_HOL_Deep/Calculus.thy#L110>) — near-exact

```isabelle
lemma infinite_inj_image: "inj f ⟹ infinite A ⟹ infinite (f ` A)"
  by (metis finite_imageD inj_on_subset subset_UNIV)
```

- **near-exact** (theorems) [Infinity\.infinite\_image\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Z_Toolkit/Infinity.thy#L102>) in [Z\_Toolkit](<https://isa-afp.org/entries/Z_Toolkit.html>) (distance 0.0262, syntactic 0.69, verdict DUPLICATE)

    Both items state the same mathematical fact: that the image of an infinite set under an injective function is infinite, differing only in notation and the specific way injectivity is expressed \(as a function property vs\. a relation property\)\.

    ```isabelle
    theorem infinite_image [intro]:
    "infinite A ⟹ inj_on f A ⟹ infinite (f ` A)"
      apply (metis finite_imageD)
      done
    ```

- **near-exact** (theorems) [RR2\_Infinite\.infinite\_inj\_image\_infinite\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Regular_Tree_Relations/RR2_Infinite.thy#L71>) in [Regular\_Tree\_Relations](<https://isa-afp.org/entries/Regular_Tree_Relations.html>) (distance 0.0274, syntactic 0.51, verdict DUPLICATE)

    Both lemmas state that the image of an infinite set under an injective function is infinite, differing only in the naming of the sets and the specific notation used for injectivity\.

    ```isabelle
    lemma infinite_inj_image_infinite:
      assumes "infinite S" and "inj_on f S"
      shows "infinite (f ` S)"
      using assms finite_image_iff by blast
    ```

- **near-exact** (theorems) [SetInterval2\.inj\_on\_imp\_infinite\_image\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/List-Infinite/CommonSet/SetInterval2.thy#L972>) in [List\-Infinite](<https://isa-afp.org/entries/List-Infinite.html>) (distance 0.0324, syntactic 0.49, verdict DUPLICATE)

    Both lemmas state that the image of an infinite set under an injective function is infinite, using different notation for injectivity \(inj vs inj\_on\) and different proof methods\.

    ```isabelle
    lemma inj_on_imp_infinite_image: "⟦ infinite A; inj_on f A ⟧ ⟹ infinite (f ` A)"
    apply (frule card_image)
    apply (fastforce simp: card_eq_0_iff)
    done
    ```

- **near-exact** (theorems) [Transcendence\_Series\.infinite\_inj\_imageE\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Transcendence_Series_Hancl_Rucki/Transcendence_Series.thy#L93>) in [Transcendence\_Series\_Hancl\_Rucki](<https://isa-afp.org/entries/Transcendence_Series_Hancl_Rucki.html>) (distance 0.0379, syntactic 0.40)

    ```isabelle
    lemma infinite_inj_imageE:
      assumes "infinite A" "inj_on f A" "f ` A ⊆ B"
      shows "infinite B"
      using assms inj_on_finite by blast
    ```

- **near-exact** (theorems) [RR2\_Infinite\.infinite\_imageD2\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Regular_Tree_Relations/RR2_Infinite.thy#L67>) in [Regular\_Tree\_Relations](<https://isa-afp.org/entries/Regular_Tree_Relations.html>) (distance 0.0383, syntactic 0.35)

    ```isabelle
    lemma infinite_imageD2:
      "infinite (f ` S) ⟹ inj f ⟹ infinite S"
      by blast
    ```

#### [Syntax\.finite\_fvs\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/HOL_in_HOL_Deep/Syntax.thy#L127>) — near-exact

```isabelle
lemma finite_fvs [simp]: "finite (fvs t)" by (induction t) auto
```

- **near-exact** (theorems) [Dtree\.finite\_dverts\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Query_Optimization/Dtree.thy#L102>) in [Query\_Optimization](<https://isa-afp.org/entries/Query_Optimization.html>) (distance 0.0708, syntactic 0.92, verdict VARIANT)

    Both lemmas state that a certain set associated with a tree \`t\` is finite, but they refer to different sets \(\`fvs\` vs \`dverts\`\), which likely represent different mathematical objects \(e\.g\., free variables vs\. divisors/descendants\) depending on the context of the theory\.

    ```isabelle
    lemma finite_dverts: "finite (dverts t)"
      by(induction t) auto
    ```

- **near-exact** (theorems) [Weighted\_Path\_Length\.finite\_nodes\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Optimal_BST/Weighted_Path_Length.thy#L43>) in [Optimal\_BST](<https://isa-afp.org/entries/Optimal_BST.html>) (distance 0.1072, syntactic 0.91, verdict RELATED)

    Both lemmas state that a certain set of elements associated with a tree structure \(either "fvs" or "nodes"\) is finite, but they refer to different sets of elements\.

    ```isabelle
    lemma finite_nodes: "finite (nodes t)"
    by(induction t) auto
    ```

#### [Syntax\.finite\_pars\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/HOL_in_HOL_Deep/Syntax.thy#L128>) — near-exact

```isabelle
lemma finite_pars [simp]: "finite (pars t)" by (induction t) auto
```

- **near-exact** (theorems) [Dtree\.finite\_dverts\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Query_Optimization/Dtree.thy#L102>) in [Query\_Optimization](<https://isa-afp.org/entries/Query_Optimization.html>) (distance 0.1545, syntactic 0.91, verdict RELATED)

    Both lemmas state that a certain property \(finiteness\) holds for a set derived from a tree \`t\`, but \`pars\` and \`dverts\` refer to different sets \(likely paths and divisors/leaves\)\.

    ```isabelle
    lemma finite_dverts: "finite (dverts t)"
      by(induction t) auto
    ```

### Simson (2026\-08\-03)

2 of 36 theorems have at least one candidate in this report.

#### [Simson\.ncol\_distinct\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Simson/Simson.thy#L96>) — near-exact

```isabelle
lemma ncol_distinct:
  assumes "¬ collinear a b c" shows "a ≠ b ∧ a ≠ c ∧ b ≠ c"
  using assms by (metis collinear_aac collinear_aba collinear_refl)
```

- **near-exact** (theorems) [Complex\_Triangles\.non\_collinear\_independant\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Morley_Theorem/Complex_Triangles.thy#L97>) in [Morley\_Theorem](<https://isa-afp.org/entries/Morley_Theorem.html>) (distance 0.0203, syntactic 0.62, verdict DUPLICATE)

    Both lemmas state that if three points are not collinear, then they must be distinct, differing only in the naming of the lemma and the order of the conjunction\.

    ```isabelle
    lemma non_collinear_independant:"¬ collinear a b c ⟹ a ≠ b ∧ b ≠ c ∧ a ≠ c"
      using collinear_ex_real by force
    ```

- **near-exact** (theorems) [Conway\_Circle\.noncollinear\_triangle\_distinct\|fact](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Conway_Circle/Conway_Circle.thy#L91>) in [Conway\_Circle](<https://isa-afp.org/entries/Conway_Circle.html>) (distance 0.0258, syntactic 0.48, verdict DUPLICATE)

    Both lemmas state that if three points are not collinear, then they must be distinct, differing only in notation \(individual arguments vs\. a set\) and variable names\.

    ```isabelle
    lemma noncollinear_triangle_distinct:
      assumes "¬ collinear {A, B, C}"
      shows "A ≠ B" "A ≠ C" "B ≠ C"
    proof -
      show "A ≠ B"
      proof
        assume "A = B"
        then have "{A, B, C} = {A, C}"
          by auto
        then have "collinear {A, B, C}"
          by simp
        with assms show False
          by contradiction
      qed
      show "A ≠ C"
      proof
        assume "A = C"
        then have "{A, B, C} = {B, C}"
          by auto
        then have "collinear {A, B, C}"
          by simp
        with assms show False
          by contradiction
      qed
      show "B ≠ C"
      proof
        assume "B = C"
        then have "{A, B, C} = {A, C}"
          by auto
        t
    ```

#### [Simson\.of\_real\_Re\_eq\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Simson/Simson.thy#L127>) — near-exact

```isabelle
lemma of_real_Re_eq: "complex_of_real (Re z) = (z + cnj z)/2"
  by (simp add: complex_add_cnj)
```

- **near-exact** (theorems) [More\_Complex\.Complex\_Re\_express\_cnj\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Complex_Geometry/More_Complex.thy#L88>) in [Complex\_Geometry](<https://isa-afp.org/entries/Complex_Geometry.html>) (distance 0.0179, syntactic 0.72, verdict DUPLICATE)

    Both lemmas state the same mathematical identity: that the complex number formed by the real part of $z$ is equal to $\(z \+ \\bar\{z\}\)/2$\.

    ```isabelle
    lemma Complex_Re_express_cnj:
      shows "Complex (Re z) 0 = (z + cnj z) / 2"
      by (cases z) (simp add: Complex_eq)
    ```

- **near-exact** (theorems) [More\_Complex\.Re\_express\_cnj\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Complex_Geometry/More_Complex.thy#L241>) in [Complex\_Geometry](<https://isa-afp.org/entries/Complex_Geometry.html>) (distance 0.0396, syntactic 0.80, verdict VARIANT)

    Item A expresses the equality in terms of the \`complex\_of\_real\` function, whereas Item B expresses the real part \`Re z\` directly; they are different formulations of the same mathematical identity\.

    ```isabelle
    lemma Re_express_cnj:
      shows "Re z = (z + cnj z) / 2"
      by (simp add: complex_add_cnj)
    ```

### Q0\_Completeness (2026\-08\-03)

6 of 178 theorems have at least one candidate in this report.

#### [Consistency\_Property\.prop\\&lt;^sub&gt;E\_Kinds\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Q0_Completeness/Consistency_Property.thy#L250>) — near-exact

```isabelle
lemma prop⇩E_Kinds:
  assumes ‹P.sat⇩E C.kind C› ‹P.sat⇩E A.kind C›  ‹P.sat⇩E B.kind C› ‹P.sat⇩E G.kind C› ‹P.sat⇩E D.kind C›
  shows ‹P.prop⇩E Kinds C›
  unfolding P.prop⇩E_def using assms by simp
```

- **near-exact** (theorems) [Example\_PIL\.prop\\&lt;^sub&gt;E\_Kinds\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Abstract_Consistency_Property/Example_PIL.thy#L727>) in [Abstract\_Consistency\_Property](<https://isa-afp.org/entries/Abstract_Consistency_Property.html>) (distance 0.0514, syntactic 0.95, verdict VARIANT)

    Item A and Item B state the same lemma structure, but Item B includes an additional assumption \(P\.sat⇩E GI\.kind C\), making it a more specific version or a variation of the property described in Item A\.

    ```isabelle
    lemma prop⇩E_Kinds:
      assumes ‹P.sat⇩E C.kind C› ‹P.sat⇩E A.kind C› ‹P.sat⇩E B.kind C› ‹P.sat⇩E GI.kind C› ‹P.sat⇩E GP.kind C› ‹P.sat⇩E D.kind C›
      shows ‹P.prop⇩E Kinds C›
      unfolding P.prop⇩E_def using assms by simp
    ```

- **near-exact** (theorems) [Example\_Bounded\_FOL\.prop\\&lt;^sub&gt;E\_Kinds\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Abstract_Consistency_Property/Example_Bounded_FOL.thy#L241>) in [Abstract\_Consistency\_Property](<https://isa-afp.org/entries/Abstract_Consistency_Property.html>) (distance 0.1163, syntactic 0.98, verdict DUPLICATE)

    The two items are identical mathematical statements; the only difference is the addition of the \`\[intro\]\` attribute in Item B\.

    ```isabelle
    lemma prop⇩E_Kinds [intro]:
      assumes ‹P.sat⇩E C.kind C› ‹P.sat⇩E A.kind C› ‹P.sat⇩E B.kind C› ‹P.sat⇩E G.kind C› ‹P.sat⇩E D.kind C›
      shows ‹P.prop⇩E Kinds C›
      unfolding P.prop⇩E_def using assms by simp
    ```

#### [Constant\_Substitution\.finite\_vars\\&lt;^sub&gt;p\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Q0_Completeness/Constant_Substitution.thy#L601>) — near-exact

```isabelle
lemma finite_vars⇩p: ‹finite (vars⇩p 𝒮)›
proof (induction 𝒮)
  case Nil
  then show ?case
    unfolding vars⇩p_def by auto
next
  case (Cons a 𝒮)
  then show ?case
    unfolding vars⇩p_def using vars_form_finiteness by auto
qed
```

- **near-exact** (theorems) [Abstract\_Linear\_Poly\.finite\_vars\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Simplex/Abstract_Linear_Poly.thy#L147>) in [Simplex](<https://isa-afp.org/entries/Simplex.html>) (distance 0.0429, syntactic 0.41, verdict DUPLICATE)

    Both lemmas state that the set of variables associated with a specific object \(likely a polynomial or a similar structure\) is finite, differing only in notation and the specific subscript used for the function\.

    ```isabelle
    lemma finite_vars: "finite (vars p)" 
      by transfer auto
    ```

- **near-exact** (theorems) [Linear\_Polynomial\.finite\_vars\_l\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Linear_Diophantine_Preprocessor/Linear_Polynomial.thy#L44>) in [Linear\_Diophantine\_Preprocessor](<https://isa-afp.org/entries/Linear_Diophantine_Preprocessor.html>) (distance 0.0460, syntactic 0.53, verdict DIFFERENT)

    Item A refers to the finiteness of the set of variables in a specific structure $\\mathcal\{S\}$ \(likely a specific instance or related to a specific construction\), whereas Item B refers to the finiteness of a set of variables associated with a parameter $p$ \(likely a list or a specific object\), and th

    ```isabelle
    lemma finite_vars_l[simp,intro]: "finite (vars_l p)" 
    proof (transfer, goal_cases)
      case (1 p)
      show ?case by (rule finite_subset[OF _ finite_imageI[OF 1, of the]], force)
    qed
    ```

#### [Model\_Existence\.MyHintikka\.fun\_ext\_vfuncset\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Q0_Completeness/Model_Existence.thy#L349>) — near-exact

```isabelle
lemma fun_ext_vfuncset:
  assumes ‹f ∈ elts (A ⟼ B)› ‹g ∈ elts (A ⟼ B)›
    and ‹⋀x. x ∈ elts A ⟹ app f x = app g x›
  shows ‹f = g›
  using assms ZFC_Cardinals.fun_ext by auto
```

- **near-exact** (theorems) [ZFC\_Cardinals\.fun\_ext\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/ZFC_in_HOL/ZFC_Cardinals.thy#L384>) in [ZFC\_in\_HOL](<https://isa-afp.org/entries/ZFC_in_HOL.html>) (distance 0.0493, syntactic 0.63, verdict DUPLICATE)

    Both lemmas state the principle of function extensionality \(that two functions are equal if they agree on all inputs\), merely using different notation for the function space \(A ⟼ B vs VPi A B\)\.

    ```isabelle
    lemma fun_ext:
      assumes "f ∈ elts (VPi A B)" "g ∈ elts (VPi A B)" "⋀x. x ∈ elts A ⟹ app f x = app g x"
      shows "f = g"
      by (metis VPi_memberD V_equalityI apply_pair assms)
    ```

#### [Q0\_Completeness\.hyp\_derivability\_implies\_validity\_general\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Q0_Completeness/Q0_Completeness.thy#L105>) — near-exact

```isabelle
theorem hyp_derivability_implies_validity_general:
  assumes ‹is_model_for ℳ 𝒢›
    and ‹∃ℋ ⊆ 𝒢. ℋ ⊢ A›
    and ‹is_general_model ℳ›
  shows ‹ℳ ⊨ A›
proof -
  from ‹∃ℋ ⊆ 𝒢. ℋ ⊢ A› obtain ℋ where ℋ: ‹is_hyps ℋ› ‹ℋ ⊆ 𝒢› ‹ℋ ⊢ A›
    by (metis is_derivable_from_hyps.cases)
  moreover from this obtain hs where hs: ‹lset hs = ℋ›
    using finite_list by blast
  ultimately have ‹⊢ hs ⊃⇧𝒬⇩⋆ A›
    using generalized_deduction_theorem by force
  with assms(3) have ‹ℳ ⊨ hs ⊃⇧𝒬⇩⋆ A›
    using derivability_from_no_hyps_theoremhood_equivalence and theoremhood_implies_validity
    by meson
  moreover from ‹ℋ
```

- **near-exact** (theorems) [Soundness\.hyp\_derivability\_implies\_validity\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Q0_Metatheory/Soundness.thy#L1530>) in [Q0\_Metatheory](<https://isa-afp.org/entries/Q0_Metatheory.html>) (distance 0.0410, syntactic 0.78, verdict VARIANT)

    Item A is a generalization of Item B because it uses existential quantification for the set of hypotheses \($\\exists\\mathcal\{H\} \\subseteq \\mathcal\{G\}$\), whereas Item B assumes the existence of a specific set of hypotheses via the predicate \`is\_hyps\`\.

    ```isabelle
    proposition hyp_derivability_implies_validity:
      assumes "is_hyps 𝒢"
      and "is_model_for ℳ 𝒢"
      and "𝒢 ⊢ A"
      and "is_general_model ℳ"
      shows "ℳ ⊨ A"
    proof -
      from assms(3) have "A ∈ wffs⇘o⇙"
        by (fact hyp_derivable_form_is_wffso)
      from ‹𝒢 ⊢ A› and ‹is_hyps 𝒢› obtain ℋ where "finite ℋ" and "ℋ ⊆ 𝒢" and "ℋ ⊢ A"
        by blast
      moreover from ‹finite ℋ› obtain hs where "lset hs = ℋ"
        using finite_list by blast
      ultimately have "⊢ hs ⊃⇧𝒬⇩⋆ A"
        using generalized_deduction_theorem by simp
      with assms(4) have "ℳ ⊨ hs ⊃⇧𝒬⇩⋆ A"
        using derivability_from_no_hyps_theoremhood_equivalence and
    ```

#### [Q0\_Completeness\.principle\_of\_explosion\_general\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Q0_Completeness/Q0_Completeness.thy#L153>) — near-exact

```isabelle
corollary principle_of_explosion_general: 
  ‹is_inconsistent_set 𝒢 ⟷ (∀A ∈ (wffs⇘o⇙). 𝒢 ⊢ A)›
  by (metis false_wff inconsistent_imp_hyps is_inconsistent_set_def 
      principle_of_explosion)
```

- **near-exact** (theorems) [Consistency\.principle\_of\_explosion\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Q0_Metatheory/Consistency.thy#L218>) in [Q0\_Metatheory](<https://isa-afp.org/entries/Q0_Metatheory.html>) (distance 0.0473, syntactic 0.44, verdict DUPLICATE)

    Both items state the same mathematical equivalence: that a set of formulas is inconsistent if and only if every formula is derivable from it\.

    ```isabelle
    proposition principle_of_explosion:
      assumes "is_hyps 𝒢"
      shows "is_inconsistent_set 𝒢 ⟷ (∀A ∈ (wffs⇘o⇙). 𝒢 ⊢ A)"
    proof
      assume "is_inconsistent_set 𝒢"
      show "∀A ∈ (wffs⇘o⇙). 𝒢 ⊢ A"
      proof
        fix A
        assume "A ∈ wffs⇘o⇙"
        from ‹is_inconsistent_set 𝒢› have "𝒢 ⊢ F⇘o⇙"
          unfolding is_inconsistent_set_def .
        then have "𝒢 ⊢ ∀𝔵⇘o⇙. 𝔵⇘o⇙"
          unfolding false_is_forall .
        with ‹A ∈ wffs⇘o⇙› have "𝒢 ⊢ ❙S {(𝔵, o) ↣ A} (𝔵⇘o⇙)"
          using "∀I" by fastforce
        then show "𝒢 ⊢ A"
          by simp
      qed
    next
      assume "∀A ∈ (wffs⇘o⇙). 𝒢 ⊢ A"
      then have "𝒢 ⊢ F⇘o⇙"
        using false_wff by (
    ```

#### [Q0\_Completeness\.hyp\_derivability\_implies\_validity2\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Q0_Completeness/Q0_Completeness.thy#L175>) — near-exact

```isabelle
lemma hyp_derivability_implies_validity2:
  assumes "is_model_for ℳ 𝒢"
  and "𝒢 ⊢ A"
  and "is_general_model ℳ"
shows "ℳ ⊨ A"
proof-
  have ‹is_hyps 𝒢›
    using assms(2)
    by (metis is_derivable_from_hyps.cases)
  thus ?thesis
    using thm_5402(2)[OF ‹is_hyps 𝒢› assms]
    by blast
qed
```

- **near-exact** (theorems) [Soundness\.hyp\_derivability\_implies\_validity\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Q0_Metatheory/Soundness.thy#L1530>) in [Q0\_Metatheory](<https://isa-afp.org/entries/Q0_Metatheory.html>) (distance 0.0863, syntactic 0.91, verdict VARIANT)

    Item B includes an additional assumption \`is\_hyps 𝒢\` which is not present in Item A, making Item B a more specific version or a slightly different formulation of the implication\.

    ```isabelle
    proposition hyp_derivability_implies_validity:
      assumes "is_hyps 𝒢"
      and "is_model_for ℳ 𝒢"
      and "𝒢 ⊢ A"
      and "is_general_model ℳ"
      shows "ℳ ⊨ A"
    proof -
      from assms(3) have "A ∈ wffs⇘o⇙"
        by (fact hyp_derivable_form_is_wffso)
      from ‹𝒢 ⊢ A› and ‹is_hyps 𝒢› obtain ℋ where "finite ℋ" and "ℋ ⊆ 𝒢" and "ℋ ⊢ A"
        by blast
      moreover from ‹finite ℋ› obtain hs where "lset hs = ℋ"
        using finite_list by blast
      ultimately have "⊢ hs ⊃⇧𝒬⇩⋆ A"
        using generalized_deduction_theorem by simp
      with assms(4) have "ℳ ⊨ hs ⊃⇧𝒬⇩⋆ A"
        using derivability_from_no_hyps_theoremhood_equivalence and
    ```

### Dinitz\_Garg\_Goemans\_Counterexample (2026\-07\-22)

0 of 41 theorems have at least one candidate in this report.

### Jacobian\_Counterexample (2026\-07\-20)

0 of 46 theorems have at least one candidate in this report.

### Right\_Forward\_Closures (2026\-07\-17)

3 of 54 theorems have at least one candidate in this report.

#### [Innermost\_Rewriting\.inn\_rstep\_cases\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Right_Forward_Closures/Innermost_Rewriting.thy#L136>) — near-exact

```isabelle
lemma inn_rstep_cases[consumes 1, case_names root nonroot]:
  "⟦(s,t) ∈ inn_rstep R; (s,t) ∈ inn_rrstep R ⟹ P; (s,t) ∈ inn_nrrstep R ⟹ P⟧ ⟹ P"
  by (auto simp: inn_rstep_iff_inn_rrstep_or_inn_nrrstep)
```

- **near-exact** (theorems) [Trs\.rstep\_cases\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/First_Order_Rewriting/Trs.thy#L858>) in [First\_Order\_Rewriting](<https://isa-afp.org/entries/First_Order_Rewriting.html>) (distance 0.0858, syntactic 0.90, verdict VARIANT)

    Item A is a specific version of Item B restricted to the "inn" \(likely "inner"\) relations, whereas Item B states the case analysis for the general relations\.

    ```isabelle
    lemma rstep_cases[consumes 1, case_names root nonroot]:
      "⟦(s,t) ∈ rstep R; (s,t) ∈ rrstep R ⟹ P; (s,t) ∈ nrrstep R ⟹ P⟧ ⟹ P"
      by (auto simp: rstep_iff_rrstep_or_nrrstep)
    ```

#### [Innermost\_Rewriting\.inn\_nrrstep\_args\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Right_Forward_Closures/Innermost_Rewriting.thy#L140>) — near-exact

```isabelle
lemma inn_nrrstep_args:
  assumes "(s, t) ∈ inn_nrrstep R"
  shows "∃f ss ts. s = Fun f ss ∧ t = Fun f ts ∧ length ss = length ts
    ∧ (∃j<length ss. (ss!j, ts!j) ∈ inn_rstep R ∧ (∀i<length ss. i ≠ j ⟶ ss!i = ts!i))"
  using assms
proof (cases, goal_cases)
  case *: (1 l r σ C)
  from *(5) obtain f bef D aft where C: "C = More f bef D aft" by (cases C, auto)
  define ss where "ss = bef @ D⟨l ⋅ σ⟩ # aft" 
  define ts where "ts = bef @ D⟨r ⋅ σ⟩ # aft" 
  define j where "j = length bef" 
  show ?thesis
  proof (intro exI conjI)
    show "s = Fun f ss" unfolding * ss_def C by simp
    show "t = F
```

- **near-exact** (theorems) [Trs\.nrrstep\_args\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/First_Order_Rewriting/Trs.thy#L904>) in [First\_Order\_Rewriting](<https://isa-afp.org/entries/First_Order_Rewriting.html>) (distance 0.0519, syntactic 0.95, verdict VARIANT)

    Item A describes a specific step type \`inn\_nrrstep\` \(likely "inner non\-reversing step"\) while Item B describes a general \`nrrstep\`, where the core difference lies in the underlying step relation \(\`inn\_rstep\` vs \`rstep\`\)\.

    ```isabelle
    lemma nrrstep_args:
      assumes "(s, t) ∈ nrrstep R"
      shows "∃f ss ts. s = Fun f ss ∧ t = Fun f ts ∧ length ss = length ts
        ∧ (∃j<length ss. (ss!j, ts!j) ∈ rstep R ∧ (∀i<length ss. i ≠ j ⟶ ss!i = ts!i))"
    proof -
      from assms obtain l r C σ where "(l, r) ∈ R" and "C ≠ □"
        and s: "s = C⟨l⋅σ⟩" and t: "t = C⟨r⋅σ⟩" unfolding nrrstep_def' by best
      from ‹C ≠ □› obtain f ss1 D ss2 where C: "C = More f ss1 D ss2" by (induct C) auto
      have "s = Fun f (ss1 @ D⟨l⋅σ⟩ # ss2)" (is "_ = Fun f ?ss") by (simp add: s C)
      moreover have "t = Fun f (ss1 @ D⟨r⋅σ⟩ # ss2)" (is "_ = Fun f ?ts") by (simp add: t C
    ```

#### [Innermost\_Rewriting\.Tinf\_imp\_SN\_inn\_nrrstep\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Right_Forward_Closures/Innermost_Rewriting.thy#L166>) — near-exact

```isabelle
lemma Tinf_imp_SN_inn_nrrstep: assumes "t ∈ Tinf (inn_rstep R)" 
  shows "SN_on (inn_nrrstep R) {t}" 
proof 
  fix g
  assume "g 0 ∈ {t}" and "∀ i. (g i, g (Suc i)) ∈ inn_nrrstep R" 
  hence steps: "⋀ i. (g i, g (Suc i)) ∈ inn_nrrstep R"
    and t: "t = g 0" by auto
  from steps[of 0] obtain f ts where g0: "g 0 = Fun f ts"
    using inn_nrrstep_nrrstep[of R] nrrstep_imp_Fun by blast
  define n where "n = length ts" 
  have "∃ ts. g i = Fun f ts ∧ length ts = n" for i
  proof (induct i)
    case 0
    show ?case unfolding g0 n_def by auto
  next
    case (Suc i)
    then obtain ts where "g i =
```

- **near-exact** (theorems) [Trs\.Tinf\_imp\_SN\_nrrstep\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/First_Order_Rewriting/Trs.thy#L2514>) in [First\_Order\_Rewriting](<https://isa-afp.org/entries/First_Order_Rewriting.html>) (distance 0.0396, syntactic 0.94, verdict VARIANT)

    Item A refers to the termination of the \`inn\_rstep\` relation, while Item B refers to the termination of the \`rstep\` relation; they are different formulations of a similar property involving the \`nrrstep\` relation\.

    ```isabelle
    lemma Tinf_imp_SN_nrrstep: assumes "t ∈ Tinf (rstep R)" 
      shows "SN_on (nrrstep R) {t}" 
    proof 
      fix g
      assume "g 0 ∈ {t}" and "∀ i. (g i, g (Suc i)) ∈ nrrstep R" 
      hence steps: "⋀ i. (g i, g (Suc i)) ∈ nrrstep R"
        and t: "t = g 0" by auto
      from steps[of 0] obtain f ts where g0: "g 0 = Fun f ts"
        using nrrstep_imp_Fun by blast
      define n where "n = length ts" 
      have "∃ ts. g i = Fun f ts ∧ length ts = n" for i
      proof (induct i)
        case 0
        show ?case unfolding g0 n_def by auto
      next
        case (Suc i)
        then obtain ts where "g i = Fun f ts" and "length ts = n" by auto
        with
    ```

### Multitape\_TM\_Substrate (2026\-07\-14)

6 of 147 theorems have at least one candidate in this report.

#### [Multitape\_Substrate\.relpow\_transI\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_TM_Substrate/Multitape_Substrate.thy#L78>) — near-exact

```isabelle
lemma relpow_transI:
  "(x, y) ∈ R^^n ⟹ (y, z) ∈ R^^m ⟹ (x, z) ∈ R^^(n + m)"
  by (simp add: relcomp.intros relpow_add)
```

- **near-exact** (theorems) [TM\_Common\.relpow\_transI\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_To_Singletape_TM/TM_Common.thy#L31>) in [Multitape\_To\_Singletape\_TM](<https://isa-afp.org/entries/Multitape_To_Singletape_TM.html>) (distance 0.0681, syntactic 0.97, verdict DUPLICATE)

    The two items are identical in mathematical content, differing only in whitespace and formatting\.

    ```isabelle
    lemma relpow_transI: "(x,y) ∈ R^^n ⟹ (y,z) ∈ R^^m ⟹ (x,z) ∈ R^^(n+m)"
      by (simp add: relcomp.intros relpow_add)
    ```

#### [Multitape\_Substrate\.relpow\_mono\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_TM_Substrate/Multitape_Substrate.thy#L82>) — near-exact

```isabelle
lemma relpow_mono: fixes R :: "'a rel"
  shows "R ⊆ S ⟹ R^^n ⊆ S^^n"
  by (induct n, auto)
```

- **near-exact** (theorems) [TM\_Common\.relpow\_mono\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_To_Singletape_TM/TM_Common.thy#L34>) in [Multitape\_To\_Singletape\_TM](<https://isa-afp.org/entries/Multitape_To_Singletape_TM.html>) (distance 0.0057, syntactic 1.00, verdict DUPLICATE)

    The two items are identical in mathematical content, differing only in formatting and whitespace\.

    ```isabelle
    lemma relpow_mono: fixes R :: "'a rel" shows "R ⊆ S ⟹ R^^n ⊆ S^^n"
      by (induct n, auto)
    ```

- **near-exact** (theorems) [Abstract\_Rewriting\.relpow\_mono\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Abstract-Rewriting/Abstract_Rewriting.thy#L36>) in [Abstract\-Rewriting](<https://isa-afp.org/entries/Abstract-Rewriting.html>) (distance 0.0269, syntactic 0.69, verdict VARIANT)

    Item A states that the relation power function is monotonic with respect to the subset relation, while Item B states the same property but uses different variable names and a slightly different formulation of the assumption\.

    ```isabelle
    lemma relpow_mono:
      fixes r :: "'a rel"
      assumes "r ⊆ r'" shows "r ^^ n ⊆ r' ^^ n"
      using assms by (induct n) auto
    ```

- **near-exact** (theorems) [Transitive\_Closure\.relpowp\_mono\|thm](<https://isabelle.in.tum.de/library/HOL/HOL/Transitive_Closure.html>) in [Isabelle/src/HOL/Transitive\_Closure\.thy](<https://isabelle.in.tum.de/library/HOL/HOL/Transitive_Closure.html>) (distance 0.0486, syntactic 0.63, verdict DUPLICATE)

    Both lemmas state the monotonicity of the relational power operation with respect to the subset relation, differing only in their notation \(set inclusion vs\. element\-wise implication\) and variable quantification\.

    ```isabelle
    lemma relpowp_mono:
      fixes x y :: 'a
      shows "(⋀x y. R x y ⟹ S x y) ⟹ (R ^^ n) x y ⟹ (S ^^ n) x y"
    by (induction n arbitrary: y) auto
    ```

#### [Multitape\_Substrate\.valid\_mttm\_s\_in\_Q\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_TM_Substrate/Multitape_Substrate.thy#L155>) — near-exact

```isabelle
lemma valid_mttm_s_in_Q:
  assumes "valid_mttm M"
  shows "s_tm M ∈ Q_tm M"
  using assms by (cases M) auto
```

- **near-exact** (theorems) [AlphabetEnlargement\_Simulation\.s\_tm\_in\_Q\_tm\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_Alphabet_Enlargement/AlphabetEnlargement_Simulation.thy#L2208>) in [Multitape\_Alphabet\_Enlargement](<https://isa-afp.org/entries/Multitape_Alphabet_Enlargement.html>) (distance 0.0343, syntactic 0.72, verdict DUPLICATE)

    Item A and Item B state the exact same mathematical fact \(that if a machine M is valid, its state transition is in its configuration space\), with Item B being a trivial application of the lemma defined in Item A\.

    ```isabelle
    lemma s_tm_in_Q_tm:
      assumes "valid_mttm M"
      shows "s_tm M ∈ Q_tm M"
      by (rule valid_mttm_s_in_Q[OF assms])
    ```

#### [Multitape\_Substrate\.valid\_mttm\_t\_in\_Q\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_TM_Substrate/Multitape_Substrate.thy#L160>) — near-exact

```isabelle
lemma valid_mttm_t_in_Q:
  assumes "valid_mttm M"
  shows "t_tm M ∈ Q_tm M"
  using assms by (cases M) auto
```

- **near-exact** (theorems) [AlphabetEnlargement\_Simulation\.s\_tm\_in\_Q\_tm\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_Alphabet_Enlargement/AlphabetEnlargement_Simulation.thy#L2208>) in [Multitape\_Alphabet\_Enlargement](<https://isa-afp.org/entries/Multitape_Alphabet_Enlargement.html>) (distance 0.0281, syntactic 0.71, verdict VARIANT)

    Item A states that a specific term $t\\\_tm\\ M$ is in $Q\\\_tm\\ M$, while Item B states that $s\\\_tm\\ M$ is in $Q\\\_tm\\ M$; given the context of MTTM \(Multi\-Tape Turing Machines\), these likely refer to different specific configurations or states \(e\.g\., a transition vs\. a state\) within the same mathematica

    ```isabelle
    lemma s_tm_in_Q_tm:
      assumes "valid_mttm M"
      shows "s_tm M ∈ Q_tm M"
      by (rule valid_mttm_s_in_Q[OF assms])
    ```

#### [Multitape\_Substrate\.valid\_mttm\_r\_in\_Q\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_TM_Substrate/Multitape_Substrate.thy#L165>) — near-exact

```isabelle
lemma valid_mttm_r_in_Q:
  assumes "valid_mttm M"
  shows "r_tm M ∈ Q_tm M"
  using assms by (cases M) auto
```

- **near-exact** (theorems) [AlphabetEnlargement\_Simulation\.s\_tm\_in\_Q\_tm\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_Alphabet_Enlargement/AlphabetEnlargement_Simulation.thy#L2208>) in [Multitape\_Alphabet\_Enlargement](<https://isa-afp.org/entries/Multitape_Alphabet_Enlargement.html>) (distance 0.0320, syntactic 0.71, verdict DIFFERENT)

    Item A asserts that the result of a specific operation \`r\_tm\` is in \`Q\_tm\`, whereas Item B asserts that the result of a different operation \`s\_tm\` is in \`Q\_tm\`\.

    ```isabelle
    lemma s_tm_in_Q_tm:
      assumes "valid_mttm M"
      shows "s_tm M ∈ Q_tm M"
      by (rule valid_mttm_s_in_Q[OF assms])
    ```

#### [Multitape\_Substrate\.finite\_UNIV\_dir\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_TM_Substrate/Multitape_Substrate.thy#L18>) — near-exact

```isabelle
lemma finite_UNIV_dir [simp, intro]: "finite (UNIV :: dir set)"
proof -
  have id: "UNIV = {L, R, N}"
    using dir.exhaust by auto
  show ?thesis unfolding id by auto
qed
```

- **near-exact** (theorems) [TM\_Common\.finite\_UNIV\_dir\|thm](<https://foss.heptapod.net/isa-afp/afp-2025-2/-/tree/branch/default/thys/Multitape_To_Singletape_TM/TM_Common.thy#L16>) in [Multitape\_To\_Singletape\_TM](<https://isa-afp.org/entries/Multitape_To_Singletape_TM.html>) (distance 0.0639, syntactic 1.00, verdict DUPLICATE)

    The two items are identical in mathematical content, differing only in the presence of the optional attribute 'intro'\.

    ```isabelle
    lemma finite_UNIV_dir[simp, intro]: "finite (UNIV :: dir set)" 
    proof -
      have id: "UNIV = {L,R,N}"
        using dir.exhaust by auto
      show ?thesis unfolding id by auto
    qed
    ```

