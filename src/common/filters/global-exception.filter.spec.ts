import { GlobalExceptionFilter } from './global-exception.filter';

describe('GlobalExceptionFilter', () => {
  let filter: GlobalExceptionFilter;

  beforeEach(() => {
    filter = new GlobalExceptionFilter();
  });

  describe('redactFields', () => {
    it('should redact password field', () => {
      const input = {
        message: 'fail',
        password: 'hunter2',
      };
      const result = filter.redactFields(input) as Record<string, unknown>;
      expect(result.password).toBe('[REDACTED]');
      expect(result.message).toBe('fail');
    });

    it('should redact token field', () => {
      const input = {
        message: 'fail',
        token: 'abc123secret',
      };
      const result = filter.redactFields(input) as Record<string, unknown>;
      expect(result.token).toBe('[REDACTED]');
    });

    it('should redact secret field', () => {
      const input = {
        message: 'fail',
        secret: 'my-secret-key',
      };
      const result = filter.redactFields(input) as Record<string, unknown>;
      expect(result.secret).toBe('[REDACTED]');
    });

    it('should redact apiKey field', () => {
      const input = {
        message: 'fail',
        apiKey: 'sk-1234567890',
      };
      const result = filter.redactFields(input) as Record<string, unknown>;
      expect(result.apiKey).toBe('[REDACTED]');
    });

    it('should redact authorization field', () => {
      const input = {
        message: 'fail',
        authorization: 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9',
      };
      const result = filter.redactFields(input) as Record<string, unknown>;
      expect(result.authorization).toBe('[REDACTED]');
    });

    it('should redact nested sensitive fields', () => {
      const input = {
        message: 'fail',
        details: {
          password: 'nested-password',
          safe: 'visible',
        },
      };
      const result = filter.redactFields(input) as Record<string, unknown>;
      const details = result.details as Record<string, unknown>;
      expect(details.password).toBe('[REDACTED]');
      expect(details.safe).toBe('visible');
    });

    it('should redact sensitive fields in arrays', () => {
      const input = {
        errors: [
          { password: 'pass1', message: 'error1' },
          { token: 'token2', message: 'error2' },
        ],
      };
      const result = filter.redactFields(input) as Record<string, unknown>;
      const errors = result.errors as Array<Record<string, unknown>>;
      expect(errors[0].password).toBe('[REDACTED]');
      expect(errors[0].message).toBe('error1');
      expect(errors[1].token).toBe('[REDACTED]');
      expect(errors[1].message).toBe('error2');
    });

    it('should handle null and undefined values', () => {
      expect(filter.redactFields(null)).toBeNull();
      expect(filter.redactFields(undefined)).toBeUndefined();
    });

    it('should handle primitive values', () => {
      expect(filter.redactFields('string')).toBe('string');
      expect(filter.redactFields(123)).toBe(123);
      expect(filter.redactFields(true)).toBe(true);
    });

    it('should handle case-insensitive field names', () => {
      const input = {
        Password: 'value1',
        TOKEN: 'value2',
        ApiKey: 'value3',
      };
      const result = filter.redactFields(input) as Record<string, unknown>;
      expect(result.Password).toBe('[REDACTED]');
      expect(result.TOKEN).toBe('[REDACTED]');
      expect(result.ApiKey).toBe('[REDACTED]');
    });

    it('should not redact non-sensitive fields', () => {
      const input = {
        message: 'error occurred',
        statusCode: 400,
        timestamp: '2026-07-26T10:00:00Z',
        path: '/api/test',
      };
      const result = filter.redactFields(input) as Record<string, unknown>;
      expect(result.message).toBe('error occurred');
      expect(result.statusCode).toBe(400);
      expect(result.timestamp).toBe('2026-07-26T10:00:00Z');
      expect(result.path).toBe('/api/test');
    });
  });
});
