/**
 * React Hooks for Entity Management
 * Uses TanStack Query for state management
 * CDN-compatible version
 */

function rmcEntityUrl(key, suffix) {
  var base = (window.RMCPlatformSurface && window.RMCPlatformSurface.url(key)) || "";
  if (!base) return "";
  return suffix ? base.replace(/\/?$/, "/") + suffix : base;
}

window.ReactHooks = {
  // Hook for fetching students (simplified for CDN)
  useStudents: (filters = {}) => {
    const [data, setData] = React.useState(null);
    const [isLoading, setIsLoading] = React.useState(true);
    const [error, setError] = React.useState(null);
    
    React.useEffect(() => {
      const fetchData = async () => {
        try {
          setIsLoading(true);
          const params = new URLSearchParams(filters).toString();
          const studentsUrl = rmcEntityUrl("entity_students", "");
          if (!studentsUrl) return;
          const result = await window.ReactHelpers.fetchWithAuth(`${studentsUrl}${params ? '?' + params : ''}`);
          setData(result);
          setError(null);
        } catch (err) {
          setError(err);
        } finally {
          setIsLoading(false);
        }
      };
      fetchData();
    }, [JSON.stringify(filters)]);
    
    return { data, isLoading, error };
  },

  // Hook for fetching teachers
  useTeachers: (filters = {}) => {
    const [data, setData] = React.useState(null);
    const [isLoading, setIsLoading] = React.useState(true);
    const [error, setError] = React.useState(null);
    
    React.useEffect(() => {
      const fetchData = async () => {
        try {
          setIsLoading(true);
          const params = new URLSearchParams(filters).toString();
          const teachersUrl = rmcEntityUrl("entity_teachers", "");
          if (!teachersUrl) return;
          const result = await window.ReactHelpers.fetchWithAuth(`${teachersUrl}${params ? '?' + params : ''}`);
          setData(result);
          setError(null);
        } catch (err) {
          setError(err);
        } finally {
          setIsLoading(false);
        }
      };
      fetchData();
    }, [JSON.stringify(filters)]);
    
    return { data, isLoading, error };
  },

  // Hook for session claims (RBAC)
  useSessionClaims: () => {
    const [data, setData] = React.useState(null);
    const [isLoading, setIsLoading] = React.useState(true);
    const [error, setError] = React.useState(null);
    
    React.useEffect(() => {
      const fetchData = async () => {
        try {
          setIsLoading(true);
          const claimsUrl = (window.RMCPlatformSurface && window.RMCPlatformSurface.url("session_claims")) || "";
          if (!claimsUrl) return;
          const result = await window.ReactHelpers.fetchWithAuth(claimsUrl);
          setData(result);
          setError(null);
        } catch (err) {
          setError(err);
        } finally {
          setIsLoading(false);
        }
      };
      fetchData();
    }, []);
    
    return { data, isLoading, error };
  },

  // Mutation hook for creating/updating students
  useStudentMutation: () => {
    const [isPending, setIsPending] = React.useState(false);
    
    const mutateAsync = async ({ id, data }) => {
      setIsPending(true);
      try {
        const base = rmcEntityUrl("entity_students", "");
        if (!base) throw new Error("entity_students URL not configured");
        const url = id ? rmcEntityUrl("entity_students", `${id}/`) : base;
        const method = id ? 'PATCH' : 'POST';
        const result = await window.ReactHelpers.fetchWithAuth(url, {
          method,
          body: JSON.stringify(data),
        });
        return result;
      } finally {
        setIsPending(false);
      }
    };
    
    return { mutateAsync, isPending };
  },

  // Mutation hook for creating/updating teachers
  useTeacherMutation: () => {
    const [isPending, setIsPending] = React.useState(false);
    
    const mutateAsync = async ({ id, data }) => {
      setIsPending(true);
      try {
        const base = rmcEntityUrl("entity_teachers", "");
        if (!base) throw new Error("entity_teachers URL not configured");
        const url = id ? rmcEntityUrl("entity_teachers", `${id}/`) : base;
        const method = id ? 'PATCH' : 'POST';
        const result = await window.ReactHelpers.fetchWithAuth(url, {
          method,
          body: JSON.stringify(data),
        });
        return result;
      } finally {
        setIsPending(false);
      }
    };
    
    return { mutateAsync, isPending };
  },

  // Mutation hook for bulk operations
  useBulkAssignMutation: () => {
    const [isPending, setIsPending] = React.useState(false);
    
    const mutateAsync = async (payload) => {
      setIsPending(true);
      try {
        const bulkUrl = (window.RMCPlatformSurface && window.RMCPlatformSurface.url("entity_students_bulk_assign")) || "";
        if (!bulkUrl) throw new Error("bulk-assign URL not configured");
        const result = await window.ReactHelpers.fetchWithAuth(bulkUrl, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        return result;
      } finally {
        setIsPending(false);
      }
    };
    
    return { mutateAsync, isPending };
  },
};
