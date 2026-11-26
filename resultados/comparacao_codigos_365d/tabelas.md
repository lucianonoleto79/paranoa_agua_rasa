## Desempenho

| | Cordel (EF P1, CBS) | fvm-cfd (VF, passo fracionário) | Água rasa (grade C, explícito) |
|---|---|---|---|
| malha | 11506 nós, 21801 triângulos (h = 80 m) | 170 × 191 células de 80 m, 5947 no lago | 170 × 191 células de 80 m, 5947 molhadas |
| incógnitas | 11506 nós × (u, v, p, φ) | 5947 células (p, C) + 11146 faces (u, v) | 5947 células molhadas (η, C) + faces (u, v) |
| Δt (s) | 744,5 | 1800 | 2,607 |
| passos | 42.361 | 17.520 | 12.097.253 |
| tempo de parede (s) | 969 | 172 | 4,82e+04 |
| ms por passo | 22,9 | 9,82 | 3,99 |
| µs por passo e por incógnita | 0,497 | 0,426 | 0,168 |
| fechamento da massa do poluente | não fechado (ver texto) | -1,4e-16 | -2,5e-10 |

## Resultados

| em t = 365 dias | Cordel (EF P1, CBS) | fvm-cfd (VF, passo fracionário) | Água rasa (grade C, explícito) |
|---|---|---|---|
| C/C0 na sonda do braço (série própria) | 1 | 1 | 1 |
| C/C0 interpolado no nó da sonda | 1 | 1 | 1 |
| C/C0 média no lago | 0,175 (+0%) | 0,176 (+0%) | 0,172 (-2%) |
| ∫ C/C0 dA (10³ m²) | 6,67e+03 | 6,69e+03 | 6,53e+03 |
| área com C/C0 ≥ 1% (km²) | 17,9 | 17,8 | 17,9 |
| área com C/C0 ≥ 0,1% (km²) | 20,1 | 19,9 | 20,1 |
| alcance de 1% no eixo (km) | 15,4 (eixo todo) (+0%) | 15,4 (eixo todo) (+0%) | 15,4 (eixo todo) (+0%) |
| alcance de 0,1% no eixo (km) | 15,4 (eixo todo) | 15,4 (eixo todo) | 15,4 (eixo todo) |
| C/C0 na sonda Braço Sul | 0,217 | 0,22 | 0,213 |
| C/C0 na sonda Corpo central | 0,128 | 0,128 | 0,118 |
| C/C0 na sonda Braço Norte | 3,09e-07 | 2,21e-07 | 3,21e-07 |
| C/C0 na sonda Barragem | 0,0239 | 0,0236 | 0,0222 |
| saiu pela barragem (% da entrada advectiva) | 0,48 | 0,46 | 0,46 |
| C/C0 mín. / máx. | 0,0e+00 / 1,000 | 5,2e-25 / 1,000 | 3,2e-22 / 1,000 |
| velocidade no nó da sonda (mm/s) | 0,487 | 0,515 | 0,481 |
| velocidade máx. no lago (cm/s) | 0,389 | 0,254 | 0,304 |

Entrada advectiva de poluente (Q·C0/H integrada, igual nos três): 6561.1×10³ m².
