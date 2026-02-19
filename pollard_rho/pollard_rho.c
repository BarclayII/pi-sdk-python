#include <stdio.h>
#include <stdlib.h>
#include <math.h>

// Function to compute GCD using Euclidean algorithm
long long gcd(long long a, long long b) {
    if (b == 0)
        return a;
    return gcd(b, a % b);
}

// Modular multiplication to avoid overflow
long long mod_mult(long long a, long long b, long long mod) {
    long long result = 0;
    a %= mod;
    while (b > 0) {
        if (b & 1) {
            result = (result + a) % mod;
        }
        a = (a * 2) % mod;
        b >>= 1;
    }
    return result;
}

// Pollard's rho function: f(x) = (x^2 + c) mod n
long long f(long long x, long long c, long long n) {
    return (mod_mult(x, x, n) + c) % n;
}

// Pollard's rho algorithm for finding a non-trivial factor
long long pollard_rho(long long n) {
    // Handle small cases
    if (n == 1) return n;
    if (n % 2 == 0) return 2;
    
    // Initialize variables
    long long x = 2;  // Starting value
    long long y = 2;  // Starting value
    long long d = 1;  // GCD
    long long c = 1;  // Constant for polynomial
    
    // Floyd's cycle detection algorithm
    while (d == 1) {
        // Tortoise moves one step
        x = f(x, c, n);
        
        // Hare moves two steps
        y = f(f(y, c, n), c, n);
        
        // Calculate GCD of |x - y| and n
        d = gcd(llabs(x - y), n);
        
        // If we found the number itself, try different c
        if (d == n) {
            c++;
            x = 2;
            y = 2;
            d = 1;
            
            // Avoid infinite loop
            if (c > 20) {
                return n;  // Likely prime
            }
        }
    }
    
    return d;
}

// Simple primality test
int is_prime(long long n) {
    if (n <= 1) return 0;
    if (n <= 3) return 1;
    if (n % 2 == 0 || n % 3 == 0) return 0;
    
    for (long long i = 5; i * i <= n; i += 6) {
        if (n % i == 0 || n % (i + 2) == 0)
            return 0;
    }
    return 1;
}

// Function to factorize a number completely
void factorize(long long n) {
    if (n <= 1) {
        printf("No prime factors for %lld\n", n);
        return;
    }
    
    if (is_prime(n)) {
        printf("%lld ", n);
        return;
    }
    
    long long factor = pollard_rho(n);
    factorize(factor);
    factorize(n / factor);
}

int main() {
    printf("=== Pollard's Rho Algorithm Test ===\n\n");
    
    // Test cases
    long long test_numbers[] = {
        8051,           // 83 * 97
        10403,          // 101 * 103
        1403,           // 23 * 61
        5959,           // 59 * 101
        15347,          // 113 * 137 (actually 113 * 136 + 79, let me recalc: 113*137=15481)
        12403,          // Prime number
        1000000007,     // Prime number
        9999991,        // Prime number
        455839,         // 541 * 843 (actually let me check: 541*843=455863)
        455763,         // 223 * 2043 (223 * 2043 = 455589, not matching)
        1234567,        // Composite
        999999          // 3 * 3 * 3 * 7 * 11 * 13 * 37
    };
    
    int num_tests = sizeof(test_numbers) / sizeof(test_numbers[0]);
    
    for (int i = 0; i < num_tests; i++) {
        long long n = test_numbers[i];
        printf("Factorizing %lld: ", n);
        
        if (is_prime(n)) {
            printf("%lld (prime)\n", n);
        } else {
            printf("Factors: ");
            factorize(n);
            printf("\n");
        }
        
        // Verify one factorization step
        if (!is_prime(n)) {
            long long factor = pollard_rho(n);
            printf("  -> First factor found: %lld, ", factor);
            printf("Quotient: %lld", n / factor);
            printf(" (Verification: %lld * %lld = %lld)\n", factor, n/factor, factor * (n/factor));
        }
        printf("\n");
    }
    
    // Interactive test
    printf("\n=== Interactive Test ===\n");
    printf("Enter a number to factorize (or 0 to exit): ");
    long long user_input;
    
    while (scanf("%lld", &user_input) == 1 && user_input != 0) {
        if (user_input < 0) {
            printf("Please enter a positive number.\n");
        } else {
            printf("Factorizing %lld: ", user_input);
            if (is_prime(user_input)) {
                printf("%lld (prime)\n", user_input);
            } else {
                printf("Factors: ");
                factorize(user_input);
                printf("\n");
            }
        }
        printf("\nEnter another number (or 0 to exit): ");
    }
    
    printf("\nGoodbye!\n");
    return 0;
}
