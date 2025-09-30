import logo from "@/assets/logo.png";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import {
  CircleUser,
  Earth,
  LibraryBig,
  Menu,
  Pickaxe,
  Settings2,
  Users,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { Link, useLocation } from "wouter";
import MenuLink from "../ui/menu-link";
import { Toaster } from "../ui/toaster";
import { TooltipProvider } from "../ui/tooltip";
import Routes from "./routes";

export function Dashboard() {
  const [location] = useLocation();
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  return (
    <TooltipProvider>
      <div className={`grid min-h-screen w-full ${
        isSidebarCollapsed
          ? "md:grid-cols-[0_1fr] lg:grid-cols-[0_1fr]"
          : "md:grid-cols-[220px_1fr] lg:grid-cols-[280px_1fr]"
      }`}>
        <div className={`hidden md:block border-r bg-muted/40 overflow-hidden`}>
          <div className="flex h-full max-h-screen flex-col gap-2">
            <div className="flex items-center justify-center border-b px-4 h-16 lg:px-6 bg-white">
              <Link
                to={"/"}
                className="flex items-center gap-2 font-semibold h-full"
              >
                <img src={logo} alt="CTDL xTRA" className="h-full w-auto" />
              </Link>
            </div>
            <div className="flex-1">
              <nav className="grid items-start px-2 text-sm font-medium lg:px-4">
                <MenuLink to={"/catalogues"} currentLocation={location}>
                  <Earth className="h-4 w-4" />
                  Catalogues
                </MenuLink>
                <MenuLink to={"/extractions"} currentLocation={location}>
                  <Pickaxe className="h-4 w-4" />
                  Extractions
                </MenuLink>
                <MenuLink to={"/datasets"} currentLocation={location}>
                  <LibraryBig className="h-4 w-4" />
                  Data Library
                </MenuLink>
                <MenuLink to={"/users"} currentLocation={location}>
                  <Users className="h-4 w-4" />
                  Users
                </MenuLink>
                <MenuLink to={"/settings"} currentLocation={location}>
                  <Settings2 className="h-4 w-4" />
                  Settings
                </MenuLink>
              </nav>
            </div>
          </div>
        </div>
        <div className="flex flex-col">
          <header className="flex h-16 items-center gap-4 border-b bg-muted/40 px-4 lg:px-6">
            <Button
              variant="outline"
              size="icon"
              className="hidden md:inline-flex"
              onClick={() => setIsSidebarCollapsed((v) => !v)}
            >
              {isSidebarCollapsed ? (
                <PanelLeftOpen className="h-5 w-5" />
              ) : (
                <PanelLeftClose className="h-5 w-5" />
              )}
              <span className="sr-only">Toggle sidebar</span>
            </Button>
            <Sheet>
              <SheetTrigger asChild>
                <Button
                  variant="outline"
                  size="icon"
                  className="shrink-0 md:hidden"
                >
                  <Menu className="h-5 w-5" />
                  <span className="sr-only">Toggle navigation menu</span>
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="flex flex-col">
                <nav className="grid gap-2 text-lg font-medium">
                  <MenuLink to={"/"} currentLocation={location} compact={true}>
                    <img src={logo} alt="CTDL xTRA" className="h-full w-auto" />
                  </MenuLink>
                  <MenuLink
                    to={"/catalogues"}
                    currentLocation={location}
                    compact={true}
                  >
                    <Earth className="h-5 w-5" />
                    Catalogues
                  </MenuLink>
                  <MenuLink
                    to={"/extractions"}
                    currentLocation={location}
                    compact={true}
                  >
                    <Pickaxe className="h-5 w-5" />
                    Extractions
                  </MenuLink>
                  <MenuLink
                    to={"/datasets"}
                    currentLocation={location}
                    compact={true}
                  >
                    <LibraryBig className="h-5 w-5" />
                    Data Library
                  </MenuLink>
                </nav>
              </SheetContent>
            </Sheet>
            <div className="w-full flex-1"></div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="secondary"
                  size="icon"
                  className="rounded-full"
                >
                  <CircleUser className="h-5 w-5" />
                  <span className="sr-only">Toggle user menu</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem asChild>
                  <Link className="cursor-pointer" to="/profile">
                    My Profile
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link className="cursor-pointer" to="/logout">
                    Logout
                  </Link>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </header>
          <main className="flex flex-1 flex-col gap-4 p-4 lg:gap-6 lg:p-6 max-w-5xl">
            <Routes />
          </main>
        </div>
        <Toaster />
      </div>
    </TooltipProvider>
  );
}
