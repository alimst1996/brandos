import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger';
import * as request from 'supertest';
import { AppModule } from '../src/app.module';
import { GlobalExceptionFilter } from '../src/common/filters/global-exception.filter';
import { TransformInterceptor } from '../src/common/interceptors/transform.interceptor';

describe('HealthController (e2e)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    app.setGlobalPrefix('api/v1');
    app.useGlobalPipes(
      new ValidationPipe({
        whitelist: true,
        forbidNonWhitelisted: true,
        transform: true,
      }),
    );
    app.useGlobalFilters(new GlobalExceptionFilter());
    app.useGlobalInterceptors(new TransformInterceptor());

    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  describe('GET /api/v1/health', () => {
    it('should return health check status wrapped in standard envelope', () => {
      return request(app.getHttpServer())
        .get('/api/v1/health')
        .expect(200)
        .expect((res) => {
          expect(res.body).toHaveProperty('success', true);
          expect(res.body).toHaveProperty('data');
          expect(res.body.data).toHaveProperty('status', 'ok');
          expect(res.body).toHaveProperty('timestamp');
          expect(res.body).toHaveProperty('path', '/api/v1/health');
        });
    });
  });

  describe('GET /api/v1/health/live', () => {
    it('should return liveness status', () => {
      return request(app.getHttpServer())
        .get('/api/v1/health/live')
        .expect(200)
        .expect((res) => {
          expect(res.body.success).toBe(true);
          expect(res.body.data.status).toBe('ok');
          expect(res.body.data).toHaveProperty('timestamp');
          expect(res.body.data).toHaveProperty('uptime');
        });
    });
  });

  describe('GET /api/v1/health/ready', () => {
    it('should return readiness status', () => {
      return request(app.getHttpServer())
        .get('/api/v1/health/ready')
        .expect(200)
        .expect((res) => {
          expect(res.body.success).toBe(true);
          expect(res.body.data.status).toBe('ok');
          expect(res.body.data).toHaveProperty('checks');
        });
    });
  });
});

describe('AppModule (e2e)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    app.setGlobalPrefix('api/v1');
    app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
    app.useGlobalFilters(new GlobalExceptionFilter());
    app.useGlobalInterceptors(new TransformInterceptor());

    // Set up Swagger for e2e testing
    const config = new DocumentBuilder()
      .setTitle('BrandOS API')
      .setDescription('BrandOS platform API')
      .setVersion('0.1.0')
      .build();
    const document = SwaggerModule.createDocument(app, config);
    SwaggerModule.setup('api/docs', app, document);

    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  it('GET /api/docs should return Swagger UI', () => {
    return request(app.getHttpServer())
      .get('/api/docs')
      .expect(200);
  });

  it('GET /nonexistent should return 404', () => {
    return request(app.getHttpServer())
      .get('/api/v1/nonexistent')
      .expect(404);
  });
});
