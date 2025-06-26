import { expect } from 'vitest';
import { AsymmetricMatcher } from '@vitest/expect';
import { distance } from 'fastest-levenshtein';
import { inspect } from 'vitest/utils';

declare module 'vitest' {
  interface ExpectStatic {
    /**
     * Matches a string with a given threshold for similarity.
     * @param expected - The expected string.
     * @param threshold - The threshold for similarity (default: 0.6).
     * @returns True if the string matches the expected string within the threshold, otherwise false.
     * 
     * @example
     * ```javascript
     * expect('hello').toEqual(expect.like('world')); // true
     * expect('hello').toEqual(expect.like('world', 0.5)); // false
     * ```
     */
    like(expected: string, threshold?: number): any;
  }
  interface Assertion<T> {
    /**
     * Matches two arrays with matching items in any order.
     * This is useful for testing that an array contains the expected items, regardless of order.
     * Sometimes it can be difficult to understand why an array is not matching, for those times
     * temporarily switching to "toEqual()" will show the exact mismatch with a diff.
     * 
     * @example
     * ```javascript
     * expect([1, 2, 3]).arrayContaining([3, 1, 2]); // true
     * expect([1, 2, 3]).arrayContaining([3, 1, 2]); // true
     * ```
     * 
     * @param expected 
     */
    arrayContaining(expected: any[]): T;
  }
}

class LikeMatcher extends AsymmetricMatcher<string> {
  constructor(private expected: string, private threshold: number = 0.6) {
    super(expected);
  }

  asymmetricMatch(str: string): boolean {
    if (typeof str !== 'string') return false;

    const levenshteinDistance = distance(str, this.expected);
    const maxLength = Math.max(str.length, this.expected.length);
    const similarity = (maxLength - levenshteinDistance) / maxLength;
    return similarity >= this.threshold;
  }

  toString(): string {
    return `like("${this.expected}")`;
  }

  getExpectedType(): string {
    return 'string';
  }

  toAsymmetricMatcher(): string {
    return `like("${this.expected}")`;
  }
}

// Add the custom matcher directly to expect
(expect as any).like = (expected: string, threshold = 0.6) => {
  return new LikeMatcher(expected, threshold);
};

// Refactored version that works with other matchers
class ArrayMatcher extends AsymmetricMatcher<any[]> {
  public extraItems: Set<number> = new Set();
  public missingItems: Set<number> = new Set();
  public message: string = '';
  constructor(private expected: any[]) {
    super(expected);
  }

  asymmetricMatch(actual: any[]): boolean {
    this.extraItems.clear();
    this.missingItems.clear();
    this.message = '';

    if (!Array.isArray(actual) || !Array.isArray(this.expected)) {
      this.message = `Expected array to be an array, but received ${typeof actual} and ${typeof this.expected}`;
      return false;
    }

    if (actual.length !== this.expected.length) {
      this.message = `Expected array to contain ${this.expected.length} items, but received array is of length ${actual.length}`;
      return false;
    }

    // Create a map to track which expected items have been matched
    const matchedIndices = new Set<number>();
    
    // For each actual item, find a matching expected item
    for (const actualItem of actual) {
      let foundMatch = false;
      
      for (let i = 0; i < this.expected.length; i++) {
        // Skip already matched items
        if (matchedIndices.has(i)) continue;
        
        const expectedItem = this.expected[i];
        
        // Check if the items match
        if (this.itemsMatch(actualItem, expectedItem)) {
          matchedIndices.add(i);
          foundMatch = true;
          break;
        } else {
          this.extraItems.add(i);
        }
      }
    }

    this.missingItems = new Set(this.expected.filter((_, i) => !matchedIndices.has(i)).map((_, i) => i));
    
    // All actual items were matched to expected items
    return this.missingItems.size === 0 && this.extraItems.size === 0;
  }
  
  private itemsMatch(actual: any, expected: any): boolean {
    // If expected is a matcher (like the .like matcher), use its asymmetricMatch method
    if (expected && typeof expected.asymmetricMatch === 'function') {
      return expected.asymmetricMatch(actual);
    }
    
    // For objects, do a property-by-property comparison
    if (typeof actual === 'object' && actual !== null && 
        typeof expected === 'object' && expected !== null) {
      
      // Get all keys from both objects
      const actualKeys = Object.keys(actual);
      const expectedKeys = Object.keys(expected);
      
      // Check if both objects have the same number of properties
      if (actualKeys.length !== expectedKeys.length) {
        return false;
      }
      
      // Check each property in the expected object
      for (const key of expectedKeys) {
        // If the actual object doesn't have this property, they don't match
        if (!(key in actual)) {
          return false;
        }
        
        // Recursively check the property values
        if (!this.itemsMatch(actual[key], expected[key])) {
          return false;
        }
      }
      
      return true;
    }
    
    // For primitives, do a simple comparison
    return actual === expected;
  }

  toString(): string {
    return `arrayContaining(${JSON.stringify(this.expected)})`;
  }

  getExpectedType(): string {
    return 'array';
  }

  toAsymmetricMatcher(): string {
    return `arrayContaining(${JSON.stringify(this.expected)})`;
  }
}

// Add the arrayContaining matcher to the expect interface
expect.extend({
  arrayContaining(received: any[], expected: any[]) {
    const matcher = new ArrayMatcher(expected);
    const pass = matcher.asymmetricMatch(received);
    
    return {
      pass,
      message: () => {
        let message = '';
        if (pass) {
          message += `Expected array not to contain items ${JSON.stringify(expected, null, 2)} in any order`;
        }

        if (!received?.length && expected?.length) {
          message += `Expected array to contain ${expected.length} items, but received array is empty. Expected:\n${JSON.stringify(expected, null, 2)}`;
        }

        if (received?.length && !expected?.length) {
          message += `Expected array to contain 0 items, but received array is not empty. Received:\n${JSON.stringify(received, null, 2)}`;
        }
        
        if (matcher.missingItems.size > 0) {
          const missingItems = expected.filter((_, i) => matcher.missingItems.has(i));
          message += `Expected array to contain these ${missingItems.length} items:\n ${JSON.stringify(missingItems, null, 2)}\n\nInstead we received:\n${JSON.stringify(received, null, 2)}`;
        }

        if (matcher.extraItems.size > 0) {
          const extraItems = received.filter((_, i) => matcher.extraItems.has(i));
          message += `Received unexpected items:\n ${JSON.stringify(extraItems, null, 2)}\n\nExpected:\n${JSON.stringify(expected, null, 2)}`;
        }

        message += `\nTip: temporarily replace "arrayContaining()" with "toEqual()" to see the exact mismatch with a diff.\n`;

        return !message 
          ? matcher.message
          : message;
      }
    };
  }
});