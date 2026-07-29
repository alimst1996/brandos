import {
  ExceptionFilter,
  Catch,
  ArgumentsHost,
  HttpException,
  HttpStatus,
  Logger,
} from '@nestjs/common';
import { Request, Response } from 'express';

interface ErrorResponse {
  statusCode: number;
  message: string | string[];
  error?: string;
  timestamp: string;
  path: string;
  requestId?: string;
}

const SENSITIVE_FIELD_REGEX = /password|token|secret|apiKey|authorization/i;

@Catch()
export class GlobalExceptionFilter implements ExceptionFilter {
  private readonly logger = new Logger(GlobalExceptionFilter.name);

  catch(exception: unknown, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse<Response>();
    const request = ctx.getRequest<Request>();

    let status = HttpStatus.INTERNAL_SERVER_ERROR;
    let message: string | string[] = 'Internal server error';
    let error = 'Internal Server Error';

    if (exception instanceof HttpException) {
      status = exception.getStatus();
      const exceptionResponse = exception.getResponse();

      if (typeof exceptionResponse === 'string') {
        message = exceptionResponse;
      } else if (typeof exceptionResponse === 'object') {
        const responseObj = exceptionResponse as Record<string, unknown>;
        message = (responseObj.message as string | string[]) || message;
        error = (responseObj.error as string) || error;
      }
    } else if (exception instanceof Error) {
      message = exception.message;
      this.logger.error(`Unhandled exception: ${exception.message}`, exception.stack);
    } else {
      this.logger.error('Unknown exception type', JSON.stringify(exception));
    }

    const errorResponse: ErrorResponse = {
      statusCode: status,
      message,
      error,
      timestamp: new Date().toISOString(),
      path: request.url,
      requestId: request.headers['x-request-id'] as string,
    };

    // Log non-5xx errors at warn level, 5xx at error level
    if (status >= 500) {
      this.logger.error(
        `${request.method} ${request.url} ${status}`,
        JSON.stringify(errorResponse),
      );
    } else {
      this.logger.warn(`${request.method} ${request.url} ${status}: ${JSON.stringify(message)}`);
    }

    const redactedResponse = this.redactFields(errorResponse);
    response.status(status).json(redactedResponse);
  }

  redactFields(obj: unknown): unknown {
    if (obj === null || obj === undefined) {
      return obj;
    }

    if (Array.isArray(obj)) {
      return obj.map((item) => this.redactFields(item));
    }

    if (typeof obj === 'object') {
      const result: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(obj)) {
        if (SENSITIVE_FIELD_REGEX.test(key)) {
          result[key] = '[REDACTED]';
        } else {
          result[key] = this.redactFields(value);
        }
      }
      return result;
    }

    return obj;
  }
}
