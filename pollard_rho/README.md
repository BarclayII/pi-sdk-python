# Pollard's Rho Algorithm Implementation in C

This is an implementation of Pollard's Rho algorithm for integer factorization in C.

## Overview

Pollard's Rho is a probabilistic factorization algorithm that is particularly efficient at finding small prime factors of composite numbers. It was invented by John Pollard in 1975.

## Algorithm Description

The algorithm uses the following key concepts:

1. **Floyd's Cycle Detection**: Uses the "tortoise and hare" method with two sequences:
   - Tortoise: x_{i+1} = f(x_i)
   - Hare: y_{i+1} = f(f(y_i))

2. **Polynomial Function**: f(x) = (x² + c) mod n, where c is a random constant

3. **GCD Calculation**: Finds factors by computing gcd(|x - y|, n)

## Features

- Finds all prime factors of a given number
- Handles large numbers (up to 64-bit unsigned integers)
- Includes primality checking
- Modular multiplication to prevent overflow
- Both automated test cases and command-line input support

## Compilation

```bash
make
```

Or manually:
```bash
gcc -Wall -Wextra -O2 -std=c99 -o pollard_rho pollard_rho.c
```

## Usage

### Run with built-in test cases:
```bash
./pollard_rho
```

### Factor specific numbers:
```bash
./pollard_rho 12345 98765 1000000
```

## Example Output

```
Pollard's Rho Algorithm - Finding Prime Factors
================================================

Factoring 8: 2 2 2 
Factoring 15: 3 5 
Factoring 77: 7 11 
Factoring 143: 11 13 
Factoring 1147: 31 37 
Factoring 8051: 83 97 
```

## Implementation Details

### Functions

- `gcd(a, b)`: Euclidean algorithm for greatest common divisor
- `mod_mult(a, b, mod)`: Modular multiplication to avoid overflow
- `f(x, c, n)`: Polynomial function used in the algorithm
- `pollard_rho(n)`: Main Pollard's Rho implementation
- `is_prime(n)`: Primality test using trial division
- `find_factors(n)`: Recursive function to find all prime factors

### Time Complexity

- Expected time: O(n^(1/4)) for finding a factor
- Space complexity: O(1)

## Limitations

- Works with 64-bit unsigned integers (max ~18 quintillion)
- Performance degrades for very large prime numbers
- May require multiple attempts (probabilistic algorithm)

## Test Results

All test cases have been verified:
- ✓ Small composite numbers (8, 15, 77, 143)
- ✓ Medium composite numbers (1147, 8051, 10403)
- ✓ Large composite numbers (455839, 1234567890)
- ✓ Prime number detection (999999937, 1000000007, 524287)

## References

- J. M. Pollard (1975). "A Monte Carlo method for factorization"
- Floyd's cycle detection algorithm

## License

This is a educational implementation for demonstration purposes.
