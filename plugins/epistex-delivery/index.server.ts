import type { PluginServerContext } from "@getpaseo/plugin/server";
import { Delivery, type DeliveryPaseo } from "./server/delivery.ts";
import { defaultOutboxDirectory, Outbox } from "./server/outbox.ts";
import { consoleLogger, contribute } from "./server/plugin.ts";

export default function (server: PluginServerContext) {
  const delivery = new Delivery({ outbox: new Outbox(defaultOutboxDirectory()), log: consoleLogger });
  return contribute(server, {
    log: consoleLogger,
    onTurnEnded: (event, context) => delivery.onTurnEnded(event, context.paseo as unknown as DeliveryPaseo),
  });
}
