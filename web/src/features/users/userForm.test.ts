import { describe, it, expect } from 'vitest';
import { validatePassword, MIN_PASSWORD_LENGTH } from './userForm';

describe('validatePassword', () => {
  it('accepts a valid password', () => {
    expect(validatePassword('secret123')).toBeNull();
  });

  it('rejects a too-short password', () => {
    expect(validatePassword('123')).toMatch(/อย่างน้อย/);
  });

  it('rejects an empty password', () => {
    expect(validatePassword('')).toMatch(/รหัสผ่าน/);
  });

  it('exposes the shared minimum length', () => {
    expect(MIN_PASSWORD_LENGTH).toBe(6);
  });
});
