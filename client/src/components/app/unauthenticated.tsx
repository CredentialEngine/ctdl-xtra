import { Redirect, Route, Switch } from "wouter";
import Login from "./login";
import { currentPathWithSearch, loginPathWithReturnTo } from "./loginRedirect";
import Logout from "./logout";

function RedirectToLogin() {
  return (
    <Redirect to={loginPathWithReturnTo(currentPathWithSearch())} replace />
  );
}

export default function Unauthenticated() {
  return (
    <div className="w-full h-dvh flex items-center justify-center">
      <Switch>
        <Route path="/" component={Login} />
        <Route path="/logout" component={Logout} />
        <Route>
          <RedirectToLogin />
        </Route>
      </Switch>
    </div>
  );
}
