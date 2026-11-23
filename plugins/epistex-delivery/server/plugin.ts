import type { PluginServerContext } from "@getpaseo/plugin/server";
import type { PluginHookContext, PluginHookPayload } from "@getpaseo/plugin/server";

export type TurnEndedEvent = PluginHookPayload<"agent.turn.after">;
export type TurnEndedHandler = (event: TurnEndedEvent, context: PluginHookContext) => Promise<void>;
export type PermissionEvent = PluginHookPayload<"agent.permission.before">;
export type PermissionHandler = (event: PermissionEvent, context: PluginHookContext) => Promise<void>;
export type OpenRequest = PluginHookPayload<"agent.open.before">["request"];
export type OpenHandler = (request: OpenRequest) => OpenRequest | void;

export interface Logger {
  info(message: string): void;
  error(message: string): void;
}

export interface ContributeOptions {
  log?: Logger;
  onTurnEnded?: TurnEndedHandler;
  onPermission?: PermissionHandler;
  onOpen?: OpenHandler;
}

export const PLUGIN_ID = "epistex-delivery";
export const PASEO_RANGE = ">=0.17.2 <0.18";

export const consoleLogger: Logger = {
  info: (message) => console.log(`[${PLUGIN_ID}] ${message}`),
  error: (message) => console.error(`[${PLUGIN_ID}] ${message}`),
};

const noop = () => {};

export const HOOKS = ["agent.turn.after", "agent.permission.before"] as const;
const OPEN_HOOK = "agent.open.before";

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
  const { onOpen } = options;
  if (onOpen) {
    try {
      const unsubscribe = context.addHook(OPEN_HOOK, async ({ request }) => {
        try {
          return onOpen(request) ?? undefined;
        } catch (error) {
          log.error(`${OPEN_HOOK} handler failed for ${request.agentId}: ${describe(error)}`);
          return undefined;
        }
      });
      if (typeof unsubscribe !== "function") throw new Error("addHook did not return an unsubscribe function");
      unsubscribes.push(unsubscribe);
      log.info(`registered ${OPEN_HOOK}`);
    } catch (error) {
      log.error(`cannot register ${OPEN_HOOK}: ${describe(error)}; agent tools are not offered, delivery stays on`);
    }
  }
  return undo;
}

export function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
