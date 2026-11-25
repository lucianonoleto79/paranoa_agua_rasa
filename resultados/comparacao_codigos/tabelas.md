## Desempenho

| | Cordel (EF P1, CBS) | fvm-cfd (VF, passo fracionário) | Água rasa (grade C, explícito) |
|---|---|---|---|
| malha | 11506 nós, 21801 triângulos (h = 80 m) | 170 × 191 células de 80 m, 5947 no lago | 170 × 191 células de 80 m, 5947 molhadas |
| incógnitas | 11506 nós × (u, v, p, φ) | 5947 células (p, C) + 11146 faces (u, v) | 5947 células molhadas (η, C) + faces (u, v) |
| Δt (s) | 743 | 1800 | 2,607 |
| passos | 814 | 336 | 232.003 |
| tempo de parede (s) | 21,2 | 3,05 | 1,02e+03 |
| ms por passo | 26 | 9,08 | 4,41 |
| µs por passo e por incógnita | 0,565 | 0,394 | 0,185 |
| fechamento da massa do poluente | não fechado (ver texto) | -4,1e-16 | 3,8e-12 |

## Resultados

| em t = 7 dias | Cordel (EF P1, CBS) | fvm-cfd (VF, passo fracionário) | Água rasa (grade C, explícito) |
|---|---|---|---|
| C/C0 na sonda do braço (série própria) | 0,00242 | 0,00195 | 0,0016 |
| C/C0 interpolado no nó da sonda | 0,00242 | 0,00221 | 0,00178 |
| C/C0 média no lago | 0,00508 (+0%) | 0,0056 (+10%) | 0,00307 (-40%) |
| ∫ C/C0 dA (10³ m²) | 194 | 213 | 117 |
| área com C/C0 ≥ 1% (km²) | 0,591 | 0,589 | 0,557 |
| área com C/C0 ≥ 0,1% (km²) | 0,762 | 0,742 | 0,736 |
| alcance de 1% no eixo (km) | 1,11 (+0%) | 1,11 (+0%) | 1,07 (-3%) |
| alcance de 0,1% no eixo (km) | 1,38 | 1,36 | 1,34 |
| C/C0 mín. / máx. | -7,7e-108 / 1,000 | 0,0e+00 / 0,973 | 0,0e+00 / 0,869 |
| velocidade no nó da sonda (mm/s) | 0,487 | 0,515 | 0,481 |
| velocidade máx. no lago (cm/s) | 0,389 | 0,254 | 0,304 |

Entrada advectiva de poluente (Q·C0/H integrada, igual nos três): 117.1×10³ m².
