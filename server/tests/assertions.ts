import { expect } from 'vitest';
import { AsymmetricMatcher } from '@vitest/expect';
import { distance } from 'fastest-levenshtein';
import { computeEmbedding } from '../src/embedding';

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


    /**
     * Asserts that two embedding vectors are similar enough based on cosine similarity.
     * @param expected - The expected embedding vector.
     * @param threshold - The minimum cosine similarity required to pass (default: 0.85).
     */
    toBeSimilarEmbedding(expected: string, threshold?: number): any;

    /**
     * Asymmetric matcher factory for embedding similarity. Use inside other matchers, e.g.
     * `expect(vec).toEqual(expect.similarEmbedding(other))`.
     */
    similarEmbedding(expected: string, threshold?: number): any;
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
    /**
     * Asserts that two embedding vectors are similar enough based on cosine similarity.
     * @param expected - The expected embedding vector.
     * @param threshold - The minimum cosine similarity required to pass (default: 0.85).
     */
    toBeSimilarEmbedding(expected: string | number[], threshold?: number): T;

    /**
     * Asserts that two embedding vectors are similar enough based on cosine similarity.
     * @param expected - The expected embedding vector.
     * @param threshold - The minimum cosine similarity required to pass (default: 0.85).
     */
    cosineSimilarity(expected: number[], threshold?: number): T;
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

class SimilarEmbeddingMatcher extends AsymmetricMatcher<string> {
  private threshold: number;
  private similarity: number | null = null;

  constructor(private expected: string, threshold: number = 0.85) {
    super(expected);
    this.threshold = threshold;
  }

  // Vitest does not support async matchers yet, Once it does we can remove the @ts-ignore
  // and use expect.toBeSimilarEmbedding within a object matcher. But for now this does not work.
  // @ts-ignore
  async asymmetricMatch(actual: string): Promise<boolean> {
    if (typeof actual !== "string" || typeof this.expected !== "string") {
      return false;
    }

    // Convert to vectors
    const { embedding: expectedVector } = await computeEmbedding(this.expected);
    const { embedding: actualVector } = await computeEmbedding(actual);

    if (expectedVector.length !== actualVector.length) {
      return false;
    }

    const dot = actualVector.reduce(
      (acc, v, i) => acc + v * expectedVector[i],
      0
    );
    const normA = Math.sqrt(actualVector.reduce((acc, v) => acc + v * v, 0));
    const normB = Math.sqrt(expectedVector.reduce((acc, v) => acc + v * v, 0));

    this.similarity = normA === 0 || normB === 0 ? 0 : dot / (normA * normB);
    return this.similarity >= this.threshold;
  }

  toString(): string {
    return `similarEmbedding(${typeof this.expected === "string" ? "\"" + this.expected + "\"" : "[vector]"}, ${this.threshold})`;
  }

  getExpectedType(): string {
    return "string";
  }

  toAsymmetricMatcher(): string {
    return this.toString();
  }

  getSimilarity(): number | null {
    return this.similarity;
  }
}

// Add the matcher factory to expect
(expect as any).similarEmbedding = (
  expected: string,
  threshold: number = 0.85
) => new SimilarEmbeddingMatcher(expected, threshold);

expect.extend({
  async toBeSimilarEmbedding(
    received: string,
    expected: string,
    threshold: number = 0.85
  ) {
    const matcher = new SimilarEmbeddingMatcher(expected, threshold);
    const pass = await matcher.asymmetricMatch(received);

    const similarity = (matcher as any).getSimilarity?.() ?? null;

    return {
      pass,
      message: () =>
        `Expected cosine similarity ${pass ? "not " : ""}to be >= ${threshold}. Actual similarity: ${
          similarity !== null ? similarity.toFixed(4) : "unknown"
        }`,
    } as any;
  },
});

expect.extend({
  cosineSimilarity(received: number[], expected: number[], threshold: number = 0.85) {
    const dot = received.reduce((acc, v, i) => acc + v * expected[i], 0);
    const normA = Math.sqrt(received.reduce((acc, v) => acc + v * v, 0));
    const normB = Math.sqrt(expected.reduce((acc, v) => acc + v * v, 0));

    const similarity = normA === 0 || normB === 0 ? 0 : dot / (normA * normB);
    return {
      pass: similarity >= threshold,
      message: () => `Expected cosine similarity ${similarity >= threshold ? "not " : ""}to be >= ${threshold}. Actual similarity: ${similarity.toFixed(4)}`,
    } as any;
  },
});