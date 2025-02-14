import { Route, Switch, useLocation } from "wouter";
import Catalogues from "./catalogues";
import CreateCatalogue from "./catalogues/create";
import CatalogueDetail from "./catalogues/detail";
import CatalogueCreateExtraction from "./catalogues/extract";
import DatasetList from "./datasets";
import DatasetCourses from "./datasets/courses";
import DatasetDetail from "./datasets/detail";
import Extractions from "./extractions";
import ExtractionDetail from "./extractions/detail";
import CrawlPageDetail from "./extractions/page";
import CrawlStepDetail from "./extractions/step";
import Logout from "./logout";
import MyProfile from "./profile";
import CreateRecipe from "./recipes/create";
import EditRecipe from "./recipes/edit";
import Settings from "./settings";
import Users from "./users";
import CreateUser from "./users/create";
import DeleteUser from "./users/delete";
import ResetUserPassword from "./users/reset-password";
import Welcome from "./welcome";
import { PropsWithChildren, useContext, useLayoutEffect } from "react";

import { SelectOrganization } from "./selectOrganization";
import { UserContext } from "@/userContext";

export function Scaffold({ children }: PropsWithChildren) {
  const [location, navigate] = useLocation();
  const { orgId, setOrgId } = useContext(UserContext);

  // useParams() should be used instead
  // however it requires the router context provider which 
  // can only be when a child of a route and that requires
  // a hefty restructuring of the app
  const uriOrg = location.match(/(?:^|\/)org\/([^\/]+)/)?.[1];

  useLayoutEffect(() => {
    if (!uriOrg) {
      console.debug({ goTo: 'orgs' });
      navigate('/organizations');
      return;
    }

    setOrgId(orgId)
  }, [uriOrg, location])
  return (
    <Switch>
      <Route path="/organizations" component={SelectOrganization} />
      <Route path="/org/:uriOrg" nest>
        { children }
      </Route>
    </Switch>
  );
}

export function Routes() {
  return (
    <Switch>
      <Route path="/" component={Welcome} />
      <Route path="/catalogues" nest>
        <Route path="/" component={Catalogues} />
        <Route path="/new" component={CreateCatalogue} />
        <Switch>
          <Route path="/:catalogueId" component={CatalogueDetail} />
          <Route path="/:catalogueId/recipes/new" component={CreateRecipe} />
          <Route
            path="/:catalogueId/recipes/:recipeId"
            component={EditRecipe}
          />
          <Route
            path="/:catalogueId/extract/:recipeId?"
            component={CatalogueCreateExtraction}
          />
        </Switch>
      </Route>
      <Route path="/extractions" nest>
        <Route path="/" component={Extractions} />
        <Switch>
          <Route path="/:extractionId" component={ExtractionDetail} />
          <Route
            path="/:extractionId/steps/:stepId/items/:crawlPageId"
            component={CrawlPageDetail}
          />
          <Route
            path="/:extractionId/steps/:stepId"
            component={CrawlStepDetail}
          />
        </Switch>
      </Route>
      <Route path="/datasets" nest>
        <Route path="/" component={DatasetList} />
        <Switch>
          <Route path="/catalogue/:catalogueId" component={DatasetDetail} />
          <Route path="/courses/:extractionId" component={DatasetCourses} />
        </Switch>
      </Route>
      <Route path="/users" nest>
        <Route path="/" component={Users} />
        <Route path="/new" component={CreateUser} />
        <Switch>
          <Route path="/:userId/reset-password" component={ResetUserPassword} />
          <Route path="/:userId/delete" component={DeleteUser} />
        </Switch>
      </Route>
      <Route path="/profile" component={MyProfile} />
      <Route path="/settings*" component={Settings} />
      <Route path="/logout" component={Logout} />
    </Switch>
  );
}
