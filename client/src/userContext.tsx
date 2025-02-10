import {
  createContext,
  FC,
  PropsWithChildren,
  useEffect,
  useMemo,
  useState
} from "react";

import { useQuery, UseQueryResult } from "@tanstack/react-query";

import { Organizations } from "@common/types";

export interface UserContextProps {
  user: any;
  userOrganizationsQuery?: UseQueryResult<Organizations[], unknown>,
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
  // const [userOrganizations, setUserOrganizations] = useState([]);
  const userOrganizationsQuery = useUserOrganizationsQuery(user?.id);

  useEffect(() => {
    if (user?.id) {
      // TODO: Call get user orgs
    }
  }, [user?.id])

  const value = useMemo(() => ({
    user,
    setUser,
    orgId,
    setOrgId,
    userOrganizationsQuery,
  }),
    [
      user?.id,
      orgId
    ]
  );
  return (
    <UserContext.Provider value={value}>
      {children}
    </UserContext.Provider>
  );
}

const useUserOrganizationsQuery = (userId: string | null) => {
  return useQuery<Organizations[]>({
    queryKey: ["user", userId], // The query depends on `userId`
    queryFn: () => { console.log('hello!') }, // Fetch function
    enabled: !!userId, // Only run query if `userId` is not null/undefined
  });
};