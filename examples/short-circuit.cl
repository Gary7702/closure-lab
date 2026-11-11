; Neither skipped branch is evaluated.
(begin
  (print "short circuit:" (and false (== (// 1 0) 0)))
  (or true missing-name))
; Printed: short circuit: false
; Result: true
