; More language calls than a typical Python recursion limit.
; Evaluator uses explicit continuation frames, not Python recursion.
(letrec (countdown (lambda (n)
  (if (== n 0) 0 (countdown (- n 1)))))
  (countdown 2000))
; Result: 0
