; Call-by-value fixed point: the Z combinator, often loosely called Y.
(define Z (lambda (f)
  ((lambda (x) (f (lambda (v) ((x x) v))))
   (lambda (x) (f (lambda (v) ((x x) v)))))))
(define factorial (Z (lambda (recur)
  (lambda (n) (if (== n 0) 1 (* n (recur (- n 1))))))))
(factorial 6)
; Result: 720
