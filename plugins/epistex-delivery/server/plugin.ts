// Plugin entry logic. Kept apart from index.server.ts so `node --test` can load it without the
// host-provided `@getpaseo/plugin` package.
import type { PluginServerContext } from "@getpaseo/plugin/server";
import type { PluginHookContext, PluginLifecycleEvents } from "@getpaseo/plugin/server";

export type TurnEndedEvent = PluginLifecycleEvents["agent.turn_ended"];
export type TurnEndedHandler = (event: TurnEndedEvent, context: PluginHookContext) => Promise<void>;

export interface Logger {
  info(message: string): void;
  error(message: string): void;
}

export interface ContributeOptions {
  log?: Logger;
  /** Handler for every `agent.turn_ended` event. Later steps supply the delivery handler. */
  onTurnEnded?: TurnEndedHandler;
}

export const PLUGIN_ID = "epistex-delivery";
/** The Paseo build the plugin was verified against. `paseo-plugin.json` carries the same pin. */
export const PASEO_VERSION = "0.14.0";

export const consoleLogger: Logger = {
  info: (message) => console.log(`[${PLUGIN_ID}] ${message}`),
  error: (message) => console.error(`[${PLUGIN_ID}] ${message}`),
};

const noop = () => {};

/**
 * Register the delivery hook. Fail closed: when the server context lacks the 0.14.0 lifecycle
 * API (`server.on`) or rejects the `agent.turn_ended` hook, log the reason, register nothing and
 * return a no-op cleanup. The plugin then stays loaded but inert; it never guesses another API.
 */
export function contribute(server: unknown, options: ContributeOptions = {}): () => void {
  const log = options.log ?? consoleLogger;
  const onTurnEnded = options.onTurnEnded ?? (async () => {});
  if (typeof server !== "object" || server === null || typeof (server as PluginServerContext).on !== "function") {
    log.error(`server context has no on(); built for Paseo ${PASEO_VERSION}; nothing registered`);
    return noop;
  }
  const context = server as PluginServerContext;
  let unsubscribe: unknown;
  try {
    unsubscribe = context.on("agent.turn_ended", async (event, hookContext) => {
      try {
        await onTurnEnded(event, hookContext);
      } catch (error) {
        log.error(`agent.turn_ended handler failed for ${event.agent.id}: ${describe(error)}`);
      }
    });
  } catch (error) {
    log.error(`cannot register agent.turn_ended: ${describe(error)}; nothing registered`);
    return noop;
  }
  if (typeof unsubscribe !== "function") {
    log.error("server.on did not return an unsubscribe function; nothing registered");
    return noop;
  }
  log.info(`registered agent.turn_ended (Paseo ${PASEO_VERSION})`);
  return () => {
    (unsubscribe as () => void)();
  };
}

export function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
