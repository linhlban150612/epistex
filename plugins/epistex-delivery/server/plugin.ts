// Plugin entry logic. Kept apart from index.server.ts so `node --test` can load it without the
// host-provided `@getpaseo/plugin` package.
import type { PluginServerContext } from "@getpaseo/plugin/server";
import type { PluginHookContext, PluginHookPayload } from "@getpaseo/plugin/server";

export type TurnEndedEvent = PluginHookPayload<"agent.turn.after">;
export type TurnEndedHandler = (event: TurnEndedEvent, context: PluginHookContext) => Promise<void>;
export type PermissionEvent = PluginHookPayload<"agent.permission.before">;
export type PermissionHandler = (event: PermissionEvent, context: PluginHookContext) => Promise<void>;

export interface Logger {
  info(message: string): void;
  error(message: string): void;
}

export interface ContributeOptions {
  log?: Logger;
  /** Handler for every `agent.turn.after` hook. Later steps supply the delivery handler. */
  onTurnEnded?: TurnEndedHandler;
  /** Handler for every `agent.permission.before` hook. */
  onPermission?: PermissionHandler;
}

export const PLUGIN_ID = "epistex-delivery";
/** The Paseo releases the plugin was verified on. `paseo-plugin.json` carries the same range. */
export const PASEO_RANGE = ">=0.15.0 <0.16";

export const consoleLogger: Logger = {
  info: (message) => console.log(`[${PLUGIN_ID}] ${message}`),
  error: (message) => console.error(`[${PLUGIN_ID}] ${message}`),
};

const noop = () => {};

/** The hooks the plugin needs, all or none: the Lead relies on both once native notifications are off. */
export const HOOKS = ["agent.turn.after", "agent.permission.before"] as const;

/**
 * Register the delivery hooks. Fail closed: when the server context lacks the 0.15 lifecycle API
 * (`server.addHook`) or rejects one of the hooks, log the reason, unregister what was registered
 * and return a no-op cleanup. The plugin then stays loaded but inert; it never guesses another API.
 */
export function contribute(server: unknown, options: ContributeOptions = {}): () => void {
  const log = options.log ?? consoleLogger;
  const onTurnEnded = options.onTurnEnded ?? (async () => {});
  const onPermission = options.onPermission ?? (async () => {});
  if (typeof server !== "object" || server === null || typeof (server as PluginServerContext).addHook !== "function") {
    log.error(`server context has no addHook(); built for Paseo ${PASEO_RANGE}; nothing registered`);
    return noop;
  }
  const context = server as PluginServerContext;
  const guard = <Event extends { agent: { id: string } }>(name: string, handler: (event: Event, hookContext: PluginHookContext) => Promise<void>) =>
    async (event: Event, hookContext: PluginHookContext) => {
      try {
        await handler(event, hookContext);
      } catch (error) {
        log.error(`${name} handler failed for ${event.agent.id}: ${describe(error)}`);
      }
    };
  const unsubscribes: Array<() => void> = [];
  const undo = () => unsubscribes.splice(0).reverse().forEach((unsubscribe) => unsubscribe());
  for (const name of HOOKS) {
    let unsubscribe: unknown;
    try {
      unsubscribe =
        name === "agent.turn.after"
          ? context.addHook(name, guard(name, onTurnEnded))
          : context.addHook(name, guard(name, onPermission));
    } catch (error) {
      undo();
      log.error(`cannot register ${name}: ${describe(error)}; nothing registered`);
      return noop;
    }
    if (typeof unsubscribe !== "function") {
      undo();
      log.error("server.addHook did not return an unsubscribe function; nothing registered");
      return noop;
    }
    unsubscribes.push(unsubscribe as () => void);
  }
  log.info(`registered ${HOOKS.join(", ")} (Paseo ${PASEO_RANGE})`);
  return undo;
}

export function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
