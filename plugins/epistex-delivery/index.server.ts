import type { PluginServerContext } from "@getpaseo/plugin/server";
import { assignTool, hostDeps } from "./server/assign.ts";
import { Delivery, LEAD_PROVIDER, type DeliveryPaseo } from "./server/delivery.ts";
import { defaultOutboxDirectory, Outbox } from "./server/outbox.ts";
import { consoleLogger, contribute } from "./server/plugin.ts";

export default function (server: PluginServerContext) {
  const delivery = new Delivery({ outbox: new Outbox(defaultOutboxDirectory()), log: consoleLogger });
  const assign = assignTool(hostDeps(consoleLogger));
  return contribute(server, {
    log: consoleLogger,
    // Lead seats get the typed assignment tool; every other session is left as it is.
    onOpen: (request) => (LEAD_PROVIDER.test(request.provider) && request.purpose === "interactive" ? { ...request, tools: [...request.tools, assign] } : undefined),
    onTurnEnded: (event, context) => delivery.onTurnEnded(event, context.paseo as unknown as DeliveryPaseo),
    onPermission: (event, context) => delivery.onPermission(event, context.paseo as unknown as DeliveryPaseo),
  });
}
