#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>

// Function to compute GCD using Euclidean algorithm
uint64_t gcd(uint64_t a, uint64_t b) {
    if (b == 0)
        return a;
    return gcd(b, a % b);
}

// Modular multiplication to avoid overflow
uint64_t mod_mult(uint64_t a, uint64_t b, uint64_t mod) {
    uint64_t result = 0;
    a %= mod;
    
    while (b > 0) {
        if (b % 2 == 1)
            result = (result + a) % mod;
        a = (a * 2) % mod;
        b /= 2;
    }
    
    return result % mod;
}

// Function f(x) = (x^2 + c) mod n
uint64_t f(uint64_t x, uint64_t c, uint64_t n) {
    return (mod_mult(x, x, n) + c) % n;
}

// Pollard's Rho algorithm for finding a non-trivial factor
uint64_t pollard_rho(uint64_t n) {
    // Handle small cases
    if (n == 1) return n;
    if (n % 2 == 0) return 2;
    
    // Initialize random values
    uint64_t x = rand() % (n - 2) + 2;
    uint64_t y = x;
    uint64_t c = rand() % (n - 1) + 1;
    uint64_t d = 1;
    
    // Loop until a factor is found
    while (d == 1) {
        // Tortoise move: x = f(x)
        x = f(x, c, n);
        
        // Hare move: y = f(f(y))
        y = f(f(y, c, n), c, n);
        
        // Calculate GCD of |x - y| and n
        d = gcd(x > y ? x - y : y - x, n);
        
        // If the cycle is detected but no factor found, restart
        if (d == n) {
            return pollard_rho(n);
        }
    }
    
    return d;
}

// Simple primality check (trial division)
int is_prime(uint64_t n) {
    if (n <= 1) return 0;
    if (n <= 3) return 1;
    if (n % 2 == 0 || n % 3 == 0) return 0;
    
    for (uint64_t i = 5; i * i <= n; i += 6) {
        if (n % i == 0 || n % (i + 2) == 0)
            return 0;
    }
    return 1;
}

// Recursive function to find all prime factors
void find_factors(uint64_t n) {
    if (n == 1) return;
    
    if (is_prime(n)) {
        printf("%lu ", n);
        return;
    }
    
    // Find a factor using Pollard's Rho
    uint64_t factor = pollard_rho(n);
    
    // Recursively factor both parts
    find_factors(factor);
    find_factors(n / factor);
}

int main(int argc, char *argv[]) {
    // Seed random number generator
    srand(time(NULL));
    
    // Test cases
    printf("Pollard's Rho Algorithm - Finding Prime Factors\n");
    printf("================================================\n\n");
    
    uint64_t test_numbers[] = {
        8,           // 2^3
        15,          // 3 * 5
        77,          // 7 * 11
        143,         // 11 * 13
        1147,        // 31 * 37
        8051,        // 83 * 97
        10403,       // 101 * 103
        455839,      // 613 * 743
        999999937,   // Prime number
        1000000007,  // Prime number
        1234567890,  // 2 * 3^2 * 5 * 3607 * 3803
    };
    
    int num_tests = sizeof(test_numbers) / sizeof(test_numbers[0]);
    
    for (int i = 0; i < num_tests; i++) {
        uint64_t n = test_numbers[i];
        printf("Factoring %lu: ", n);
        
        if (is_prime(n)) {
            printf("%lu (prime)\n", n);
        } else {
            find_factors(n);
            printf("\n");
        }
    }
    
    // Interactive mode
    if (argc > 1) {
        printf("\n");
        for (int i = 1; i < argc; i++) {
            uint64_t n = strtoull(argv[i], NULL, 10);
            printf("Factoring %lu: ", n);
            
            if (is_prime(n)) {
                printf("%lu (prime)\n", n);
            } else {
                find_factors(n);
                printf("\n");
            }
        }
    }
    
    return 0;
}
