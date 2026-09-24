import { Logo } from '../components/Logo';
import { useRailTooltip } from './useRailTooltip';
import { searchGroups } from './search-items';
import type { Route } from './useRoute';
const routes = ['recordings', 'analysis', 'processing'];
const navigation = routes.map((route) => ({
  route,
  label: route[0].toUpperCase() + route.slice(1),
  icon: searchGroups[0].items.find(
    (item) =>
      item.route ===
      (route === 'analysis' ? 'processing' : route === 'processing' ? 'analysis' : route),
  )!.icon,
}));
export function Sidebar({ route }: { route: Route }) {
  const { events, tooltip } = useRailTooltip();
  return (
    <>
      <div
        {...events}
        className="group peer text-sidebar-foreground md:block"
        data-collapsible="icon"
        data-side="left"
        data-slot="sidebar"
        data-state="collapsed"
        data-variant="inset"
      >
        <div
          className="cn-sidebar-gap relative w-(--sidebar-width) bg-transparent group-data-[collapsible=offExamples]:w-0 group-data-[side=right]:rotate-180 group-data-[collapsible=icon]:w-[calc(var(--sidebar-width-icon)+(--spacing(4)))]"
          data-slot="sidebar-gap"
        ></div>
        <div
          className="fixed inset-y-0 z-10 flex h-svh w-(--sidebar-width) transition-[left,right,width] md:flex left-0 group-data-[collapsible=offExamples]:left-[calc(var(--sidebar-width)*-1)] p-2 *:data-[slot=sidebar-inner]:bg-transparent group-data-[collapsible=icon]:w-[calc(var(--sidebar-width-icon)+(--spacing(4)))] duration-(--sidebar-animation-duration) ease-(--sidebar-animation-ease)"
          data-slot="sidebar-container"
        >
          <div
            className="cn-sidebar-inner flex size-full flex-col"
            data-sidebar="sidebar"
            data-slot="sidebar-inner"
          >
            <div
              className="cn-sidebar-header flex flex-col pt-0"
              data-sidebar="header"
              data-slot="sidebar-header"
            >
              <div className="flex h-12 items-center justify-between">
                <a
                  href="#/recordings"
                  className="cn-button group/button inline-flex shrink-0 select-none items-center justify-center whitespace-nowrap outline-none disabled:pointer-events-none disabled:opacity-50 [&amp;_svg]:pointer-events-none [&amp;_svg]:shrink-0 cn-button-variant-ghost cn-button-size-icon transition-opacity duration-(--sidebar-animation-duration) ease-(--sidebar-animation-ease)"
                  data-size="icon"
                  data-slot="button"
                  data-variant="ghost"
                  aria-label="Tectrace home"
                  data-rail-logo=""
                >
                  <Logo />
                  <span className="sr-only">{'Tectrace'}</span>
                </a>
              </div>
            </div>
            <div
              className="cn-sidebar-content flex min-h-0 flex-1 flex-col overflow-auto group-data-[collapsible=icon]:overflow-hidden"
              data-sidebar="content"
              data-slot="sidebar-content"
            >
              <div
                className="cn-sidebar-group relative flex w-full min-w-0 flex-col"
                data-sidebar="group"
                data-slot="sidebar-group"
              >
                <ul
                  className="cn-sidebar-menu flex w-full min-w-0 flex-col"
                  data-sidebar="menu"
                  data-slot="sidebar-menu"
                >
                  {navigation.map((item) => (
                    <li
                      key={item.route}
                      className="group/menu-item relative group/collapsible"
                      data-sidebar="menu-item"
                      data-slot="collapsible"
                      data-state="open"
                    >
                      <a
                        href={`#/${item.route}`}
                        className="cn-sidebar-menu-button peer/menu-button flex w-full items-center overflow-hidden outline-hidden disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50 [&amp;_svg]:size-4 [&amp;_svg]:shrink-0 cn-sidebar-menu-button-variant-default cn-sidebar-menu-button-size-default font-normal text-muted-foreground! [&amp;>span:last-child]:text-clip [&amp;>span]:text-nowrap data-[active=true]:text-sidebar-accent-foreground! duration-[calc(var(--sidebar-animation-duration)*0.5)] ease-(--sidebar-animation-ease) group-data-[collapsible=icon]:duration-(--sidebar-animation-duration)"
                        data-active={String(route === item.route)}
                        aria-current={route === item.route ? 'page' : undefined}
                        data-sidebar="menu-button"
                        data-size="default"
                        data-slot="sidebar-menu-button"
                        data-state="closed"
                        data-rail-link=""
                        aria-label={item.label}
                      >
                        {item.icon}
                        <span>{item.label}</span>
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
      {tooltip}
    </>
  );
}
