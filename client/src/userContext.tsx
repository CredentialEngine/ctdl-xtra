import {
  createContext,
  FC,
  PropsWithChildren,
  useMemo,
  useState
} from "react";
import { UseTRPCQueryResult } from "@trpc/react-query/shared";
import { TRPCClientErrorLike } from '@trpc/react-query';
import { trpc, AppRouter, RouterOutput } from "./utils";

type UserOrgs = RouterOutput['orgs']['ofCurrentUser'];
type UserOrgsQuery = UseTRPCQueryResult<UserOrgs, TRPCClientErrorLike<AppRouter>>;

export interface UserContextProps {
  user: any;
  userOrgsQuery?: UserOrgsQuery,
  setUser: React.Dispatch<any>;
  currentOrganizationId?: number;
  setCurrentOrganizationId: React.Dispatch<this['currentOrganizationId']>;
  currentOrganization?: UserOrgs[number];
}

export const UserContext = createContext<UserContextProps>({
  user: null,
  setUser: () => { },
  setCurrentOrganizationId: () => { }
});

export const UserProvider: FC<PropsWithChildren> = ({ children }) => {
  const [user, setUser] = useState<any>();
  const [currentOrganizationId, setCurrentOrganizationId] = useState<UserContextProps['currentOrganizationId']>();
  const userOrgsQuery = trpc.orgs.ofCurrentUser.useQuery(undefined, {
    enabled: !!user?.id,
  });
  const currentOrganization = userOrgsQuery?.data?.find(org => org.orgs.id === currentOrganizationId);

  const value = useMemo(() => ({
    user,
    setUser: (user: any) => {
      console.trace(`setting user`);
      setUser(user);
    },
    currentOrganization,
    currentOrganizationId,
    setCurrentOrganizationId: (id: any) => {
      console.trace(`set ID state`);
      setCurrentOrganizationId(id);
    },
    userOrgsQuery,
  }),
    [
      user?.id,
      currentOrganizationId,
      userOrgsQuery?.status,
    ]
  );
  return (
    <UserContext.Provider value={value}>
      {children}
    </UserContext.Provider>
  );
}