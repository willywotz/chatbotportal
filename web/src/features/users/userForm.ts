export const MIN_PASSWORD_LENGTH = 6;

/** Returns an error message (Thai) or null when the password is valid. */
export function validatePassword(password: string): string | null {
  if (!password) return 'กรุณากรอกรหัสผ่าน';
  if (password.length < MIN_PASSWORD_LENGTH) return 'รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร';
  return null;
}
