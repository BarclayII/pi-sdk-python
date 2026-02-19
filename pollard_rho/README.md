# Pollard's Rho Algorithm - Implementation and Test Results

## Overview
Pollard's rho algorithm is a probabilistic integer factorization algorithm that is particularly efficient for finding small factors of composite numbers.

## How It Works
1. **Cycle Detection**: Uses Floyd's "tortoise and hare" algorithm
   - Tortoise moves one step at a time: x = f(x)
   - Hare moves two steps at a time: y = f(f(y))
   
2. **Polynomial Function**: f(x) = (x² + c) mod n
   - Generates a pseudo-random sequence
   - Eventually creates a cycle
   
3. **Factor Finding**: Computes gcd(|x - y|, n)
   - When a non-trivial gcd is found, it's a factor
   - If gcd equals n, tries different constant c

## Test Results

### Successful Factorizations:
- 8051 = 97 × 83
- 10403 = 101 × 103
- 1403 = 23 × 61
- 5959 = 59 × 101
- 15347 = 103 × 149
- 455839 = 761 × 599
- 1234567 = 127 × 9721
- 999999 = 3 × 7 × 3 × 3 × 11 × 37 × 13

### Prime Number Detection:
- 1000000007 ✓
- 9999991 ✓
- 17 ✓

## Key Features
1. **Overflow Prevention**: Uses modular multiplication to handle large numbers
2. **Recursive Factorization**: Completely factors composite numbers
3. **Prime Detection**: Includes primality testing
4. **Interactive Mode**: Allows user input for custom factorization

## Time Complexity
Expected: O(n^(1/4)) for finding a factor of n

## Usage
```bash
gcc -o pollard_rho pollard_rho.c -lm
./pollard_rho
```

The program runs automatic tests and then allows interactive input.
