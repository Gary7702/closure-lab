; A closure remembers the definition environment, not the caller's scope.
(define make-adder (lambda (x) (lambda (y) (+ x y))))
(define add-seven (make-adder 7))
(let (x 1000) (add-seven 5))
; Result: 12
