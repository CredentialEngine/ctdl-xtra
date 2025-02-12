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
  orgId?: number;
  setOrgId: React.Dispatch<this['orgId']>;
}

export const UserContext = createContext<UserContextProps>({
  user: null,
  setUser: () => { },
  setOrgId: () => { }
});

export const UserProvider: FC<PropsWithChildren> = ({ children }) => {
  const [user, setUser] = useState<any>();
  const [orgId, setOrgId] = useState<UserContextProps['orgId']>();
  const userOrgsQuery = trpc.orgs.ofCurrentUser.useQuery(undefined, {
    enabled: !!user?.id,
  });

  const value = useMemo(() => ({
    user,
    setUser,
    orgId,
    setOrgId,
    userOrgsQuery,
  }),
    [
      user?.id,
      orgId,
      userOrgsQuery?.isLoading
    ]
  );
  return (
    <UserContext.Provider value={value}>
      {children}
    </UserContext.Provider>
  );
}