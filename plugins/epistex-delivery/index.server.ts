import type { PluginServerContext } from "@getpaseo/plugin/server";
import { contribute } from "./server/plugin.ts";

export default function (server: PluginServerContext) {
  return contribute(server);
}
