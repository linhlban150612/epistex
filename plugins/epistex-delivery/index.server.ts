import type { PluginServerContext } from "@getpaseo/plugin/server";
import { assignTool, hostDeps } from "./server/assign.ts";
import { Delivery, LEAD_PROVIDER, type DeliveryPaseo } from "./server/delivery.ts";
import { defaultOutboxDirectory, Outbox } from "./server/outbox.ts";
import { consoleLogger, contribute } from "./server/plugin.ts";
import { hostDeps as submitDeps, PEER_SEAT, submitTool } from "./server/submit.ts";

export default function (server: PluginServerContext) {
  const outbox = new Outbox(defaultOutboxDirectory());
  const delivery = new Delivery({ outbox, log: consoleLogger });
  const assign = assignTool(hostDeps(consoleLogger));
  // The outbox is loaded on the first lifecycle event; a tool call can come first.
  const submit = submitTool(submitDeps(consoleLogger, async (peerAgentId, submission) => (await delivery.ready(), outbox.setSubmission(peerAgentId, submission))));
  return contribute(server, {
    log: consoleLogger,
    // Lead seats get the typed assignment tool, Peer seats the typed handoff tool; every other session is left as it is.
    onOpen: (request) => {
      if (request.purpose !== "interactive") return undefined;
      const tool = LEAD_PROVIDER.test(request.provider) ? assign : PEER_SEAT.test(request.provider) ? submit : null;
      return tool ? { ...request, tools: [...request.tools, tool] } : undefined;
    },
    onTurnEnded: (event, context) => delivery.onTurnEnded(event, context.paseo as unknown as DeliveryPaseo),
    onPermission: (event, context) => delivery.onPermission(event, context.paseo as unknown as DeliveryPaseo),
  });
}
