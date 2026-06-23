import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { cn } from "@/lib/cn";
/**
 * Infinite horizontal marquee. Renders the children twice and translates -50%
 * so the loop is seamless. Pauses on hover; edges fade via a mask.
 */
export function Marquee({ children, className }) {
    return (_jsxs("div", { className: cn("group relative flex overflow-hidden", "[mask-image:linear-gradient(to_right,transparent,black_8%,black_92%,transparent)]", className), children: [_jsx("div", { className: "flex shrink-0 animate-marquee items-center gap-4 pr-4 group-hover:[animation-play-state:paused]", children: children }), _jsx("div", { "aria-hidden": true, className: "flex shrink-0 animate-marquee items-center gap-4 pr-4 group-hover:[animation-play-state:paused]", children: children })] }));
}
