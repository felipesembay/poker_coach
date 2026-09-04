import { createFileRoute, Outlet } from "@tanstack/react-router";

export const Route = createFileRoute("/push-fold")({
  component: () => <Outlet />,
});
