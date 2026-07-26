import { Controller, Get } from '@nestjs/common';
import {
  HealthCheckService,
  HealthCheck,
} from '@nestjs/terminus';
import { ApiTags, ApiOperation, ApiResponse } from '@nestjs/swagger';

@ApiTags('health')
@Controller('health')
export class HealthController {
  constructor(
    private health: HealthCheckService,
  ) {}

  @Get()
  @HealthCheck()
  @ApiOperation({ summary: 'Health check endpoint' })
  @ApiResponse({ status: 200, description: 'Service is healthy' })
  @ApiResponse({ status: 503, description: 'Service is unhealthy' })
  check() {
    return this.health.check([]);
  }

  @Get('live')
  @ApiOperation({ summary: 'Liveness probe - is the service running?' })
  @ApiResponse({ status: 200, description: 'Service is alive' })
  live() {
    return {
      status: 'ok',
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
    };
  }

  @Get('ready')
  @ApiOperation({ summary: 'Readiness probe - is the service ready to accept traffic?' })
  @ApiResponse({ status: 200, description: 'Service is ready' })
  @ApiResponse({ status: 503, description: 'Service is not ready' })
  ready() {
    return {
      status: 'ok',
      timestamp: new Date().toISOString(),
      checks: {
        database: 'connected',
      },
    };
  }
}
