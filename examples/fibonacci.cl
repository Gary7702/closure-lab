; The simple recursive algorithm is deliberately not presented as efficient.
(letrec (fib (lambda (n)
  (if (< n 2) n (+ (fib (- n 1)) (fib (- n 2))))))
  (fib 10))
; Result: 55
