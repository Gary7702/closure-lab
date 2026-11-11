; Named recursion with an explicitly recursive lexical binding.
(letrec (factorial (lambda (n)
  (if (== n 0) 1 (* n (factorial (- n 1))))))
  (factorial 7))
; Result: 5040
