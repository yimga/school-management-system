/**
 * React Hooks for Entity Management
 * Uses TanStack Query for state management
 * CDN-compatible version
 */

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
          const result = await window.ReactHelpers.fetchWithAuth(`/api/entities/students/${params ? '?' + params : ''}`);
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
          const result = await window.ReactHelpers.fetchWithAuth(`/api/entities/teachers/${params ? '?' + params : ''}`);
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
          const result = await window.ReactHelpers.fetchWithAuth('/api/session/claims/');
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
        const url = id ? `/api/entities/students/${id}/` : '/api/entities/students/';
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
        const url = id ? `/api/entities/teachers/${id}/` : '/api/entities/teachers/';
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
        const result = await window.ReactHelpers.fetchWithAuth('/api/entities/students/bulk-assign/', {
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
