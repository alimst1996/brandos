import { TransformInterceptor } from './transform.interceptor';
import { ExecutionContext, CallHandler } from '@nestjs/common';
import { of } from 'rxjs';

describe('TransformInterceptor', () => {
  let interceptor: TransformInterceptor<any>;

  beforeEach(() => {
    interceptor = new TransformInterceptor();
  });

  it('should transform response with success wrapper', (done) => {
    const mockRequest = { url: '/test' };
    const mockContext = {
      switchToHttp: jest.fn().mockReturnValue({
        getRequest: jest.fn().mockReturnValue(mockRequest),
      }),
    } as unknown as ExecutionContext;

    const mockCallHandler = {
      handle: jest.fn().mockReturnValue(of({ id: 1, name: 'test' })),
    } as CallHandler;

    interceptor.intercept(mockContext, mockCallHandler).subscribe((result) => {
      expect(result).toHaveProperty('success', true);
      expect(result).toHaveProperty('data', { id: 1, name: 'test' });
      expect(result).toHaveProperty('timestamp');
      expect(result).toHaveProperty('path', '/test');
      done();
    });
  });

  it('should handle null data', (done) => {
    const mockRequest = { url: '/test' };
    const mockContext = {
      switchToHttp: jest.fn().mockReturnValue({
        getRequest: jest.fn().mockReturnValue(mockRequest),
      }),
    } as unknown as ExecutionContext;

    const mockCallHandler = {
      handle: jest.fn().mockReturnValue(of(null)),
    } as CallHandler;

    interceptor.intercept(mockContext, mockCallHandler).subscribe((result) => {
      expect(result).toHaveProperty('success', true);
      expect(result).toHaveProperty('data', null);
      done();
    });
  });
});
