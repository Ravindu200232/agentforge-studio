/**
 * Which page shows which command: `<command set>/<command id>` to the page written for it. A command without a page
 * is laid out automatically (see `CommandPage`). The commands themselves are data, in `prompts/deployment/monitors.json`.
 */
import VercelAccount from './vercel/VercelAccount'
import VercelTeams from './vercel/VercelTeams'
import VercelTeamMembers from './vercel/VercelTeamMembers'
import VercelTokens from './vercel/VercelTokens'
import VercelContract from './vercel/VercelContract'
import VercelActivity from './vercel/VercelActivity'
import VercelEventTypes from './vercel/VercelEventTypes'
import VercelTelemetry from './vercel/VercelTelemetry'
import VercelProject from './vercel/VercelProject'
import VercelProjects from './vercel/VercelProjects'
import VercelProjectMembers from './vercel/VercelProjectMembers'
import VercelChecks from './vercel/VercelChecks'
import VercelProtection from './vercel/VercelProtection'
import VercelTargets from './vercel/VercelTargets'
import VercelDeployments from './vercel/VercelDeployments'
import VercelDeployment from './vercel/VercelDeployment'
import VercelAliases from './vercel/VercelAliases'
import VercelRoutes from './vercel/VercelRoutes'
import VercelBuildLogs from './vercel/VercelBuildLogs'
import VercelRuntimeLogs from './vercel/VercelRuntimeLogs'
import VercelVariables from './vercel/VercelVariables'
import VercelDomains from './vercel/VercelDomains'
import VercelDns from './vercel/VercelDns'
import VercelCerts from './vercel/VercelCerts'
import VercelCron from './vercel/VercelCron'
import VercelHooks from './vercel/VercelHooks'
import VercelWebhooks from './vercel/VercelWebhooks'
import VercelFlags from './vercel/VercelFlags'
import VercelIntegrations from './vercel/VercelIntegrations'
import VercelStorage from './vercel/VercelStorage'
import VercelBudgets from './vercel/VercelBudgets'
import VercelFirewall from './vercel/VercelFirewall'
import VercelGlobalConfig from './vercel/VercelGlobalConfig'
import VercelMetrics from './vercel/VercelMetrics'
import VercelAlerts from './vercel/VercelAlerts'
import GithubAccount from './github/GithubAccount'
import GithubRepository from './github/GithubRepository'
import GithubPeople from './github/GithubPeople'
import GithubCommits from './github/GithubCommits'
import GithubBranches from './github/GithubBranches'
import GithubTags from './github/GithubTags'
import GithubWorkingTree from './github/GithubWorkingTree'
import GithubAuthors from './github/GithubAuthors'
import GithubReleases from './github/GithubReleases'
import GithubPulls from './github/GithubPulls'
import GithubIssues from './github/GithubIssues'
import GithubRuns from './github/GithubRuns'
import GithubWorkflows from './github/GithubWorkflows'
import GithubSecrets from './github/GithubSecrets'
import GithubCaches from './github/GithubCaches'
import GithubKeys from './github/GithubKeys'
import NetlifyAccount from './netlify/NetlifyAccount'
import NetlifySites from './netlify/NetlifySites'
import NetlifySite from './netlify/NetlifySite'
import NetlifyDeploys from './netlify/NetlifyDeploys'
import NetlifyDeploy from './netlify/NetlifyDeploy'
import NetlifyBuilds from './netlify/NetlifyBuilds'
import NetlifyFunctions from './netlify/NetlifyFunctions'
import NetlifyForms from './netlify/NetlifyForms'
import AwsAccount from './aws/AwsAccount'
import AwsStack from './aws/AwsStack'
import AwsStackResources from './aws/AwsStackResources'
import AwsStackEvents from './aws/AwsStackEvents'
import AwsCloudFront from './aws/AwsCloudFront'
import AwsAlarms from './aws/AwsAlarms'
import AwsInstance from './aws/AwsInstance'
import AwsInstanceHealth from './aws/AwsInstanceHealth'
import AwsVolumes from './aws/AwsVolumes'
import AwsElasticIps from './aws/AwsElasticIps'
import AwsSsmAgent from './aws/AwsSsmAgent'
import AwsReleaseCommands from './aws/AwsReleaseCommands'
import AwsReleaseArtifacts from './aws/AwsReleaseArtifacts'
import AwsSecrets from './aws/AwsSecrets'
import AwsLogs from './aws/AwsLogs'
import AwsEcsCluster from './aws/AwsEcsCluster'
import AwsEcsService from './aws/AwsEcsService'
import AwsEcsServiceEvents from './aws/AwsEcsServiceEvents'
import AwsEcsTasks from './aws/AwsEcsTasks'
import AwsEcsTaskDefinition from './aws/AwsEcsTaskDefinition'
import AwsAutoScaling from './aws/AwsAutoScaling'
import AwsTargetHealth from './aws/AwsTargetHealth'
import AwsImages from './aws/AwsImages'
import AwsImageBuilds from './aws/AwsImageBuilds'
import AzureAccount from './azure/AzureAccount'
import AzureResources from './azure/AzureResources'
import AzureWebApp from './azure/AzureWebApp'
import AzurePlan from './azure/AzurePlan'
import AzureSlots from './azure/AzureSlots'
import AzureAutoscale from './azure/AzureAutoscale'
import AzureConfig from './azure/AzureConfig'
import AzureSettings from './azure/AzureSettings'
import AzureDomains from './azure/AzureDomains'
import AzureCertificates from './azure/AzureCertificates'
import AzureDeploymentLog from './azure/AzureDeploymentLog'
import AzureLiveLogs from './azure/AzureLiveLogs'

export const PAGES = {
  'vercel/account': VercelAccount,
  'vercel/teams': VercelTeams,
  'vercel/team-members': VercelTeamMembers,
  'vercel/tokens': VercelTokens,
  'vercel/contract': VercelContract,
  'vercel/activity': VercelActivity,
  'vercel/event-types': VercelEventTypes,
  'vercel/telemetry': VercelTelemetry,
  'vercel/project': VercelProject,
  'vercel/projects': VercelProjects,
  'vercel/project-members': VercelProjectMembers,
  'vercel/checks': VercelChecks,
  'vercel/protection': VercelProtection,
  'vercel/targets': VercelTargets,
  'vercel/deployments': VercelDeployments,
  'vercel/deployment': VercelDeployment,
  'vercel/aliases': VercelAliases,
  'vercel/routes': VercelRoutes,
  'vercel/build-logs': VercelBuildLogs,
  'vercel/runtime-logs': VercelRuntimeLogs,
  'vercel/variables': VercelVariables,
  'vercel/domains': VercelDomains,
  'vercel/dns': VercelDns,
  'vercel/certs': VercelCerts,
  'vercel/cron': VercelCron,
  'vercel/hooks': VercelHooks,
  'vercel/webhooks': VercelWebhooks,
  'vercel/flags': VercelFlags,
  'vercel/integrations': VercelIntegrations,
  'vercel/storage': VercelStorage,
  'vercel/budgets': VercelBudgets,
  'vercel/firewall': VercelFirewall,
  'vercel/global-config': VercelGlobalConfig,
  'vercel/metrics': VercelMetrics,
  'vercel/alerts': VercelAlerts,
  'github/gh-account': GithubAccount,
  'github/gh-repo': GithubRepository,
  'github/gh-people': GithubPeople,
  'github/gh-commits': GithubCommits,
  'github/gh-branches': GithubBranches,
  'github/gh-tags': GithubTags,
  'github/gh-status': GithubWorkingTree,
  'github/gh-authors': GithubAuthors,
  'github/gh-releases': GithubReleases,
  'github/gh-pulls': GithubPulls,
  'github/gh-issues': GithubIssues,
  'github/gh-runs': GithubRuns,
  'github/gh-workflows': GithubWorkflows,
  'github/gh-secrets': GithubSecrets,
  'github/gh-caches': GithubCaches,
  'github/gh-keys': GithubKeys,
  'netlify/netlify-account': NetlifyAccount,
  'netlify/sites': NetlifySites,
  'netlify/site': NetlifySite,
  'netlify/deploys': NetlifyDeploys,
  'netlify/site-deploy': NetlifyDeploy,
  'netlify/builds': NetlifyBuilds,
  'netlify/functions': NetlifyFunctions,
  'netlify/forms': NetlifyForms,
  'aws-account/aws-account': AwsAccount,
  'aws-account/stack': AwsStack,
  'aws-account/stack-resources': AwsStackResources,
  'aws-account/stack-events': AwsStackEvents,
  'aws-account/cdn': AwsCloudFront,
  'aws-account/alarms': AwsAlarms,
  'aws-ec2/instance': AwsInstance,
  'aws-ec2/health': AwsInstanceHealth,
  'aws-ec2/volumes': AwsVolumes,
  'aws-ec2/addresses': AwsElasticIps,
  'aws-ec2/ssm': AwsSsmAgent,
  'aws-ec2/ssm-history': AwsReleaseCommands,
  'aws-ec2/releases': AwsReleaseArtifacts,
  'aws-ec2/secrets': AwsSecrets,
  'aws-ec2/ec2-logs': AwsLogs,
  'aws-ecs/secrets': AwsSecrets,
  'aws-ecs/ecs-logs': AwsLogs,
  'aws-ecs/cluster': AwsEcsCluster,
  'aws-ecs/service': AwsEcsService,
  'aws-ecs/service-events': AwsEcsServiceEvents,
  'aws-ecs/tasks': AwsEcsTasks,
  'aws-ecs/task-definition': AwsEcsTaskDefinition,
  'aws-ecs/scaling': AwsAutoScaling,
  'aws-ecs/target-health': AwsTargetHealth,
  'aws-ecs/images': AwsImages,
  'aws-ecs/image-builds': AwsImageBuilds,
  'azure/azure-account': AzureAccount,
  'azure/resources': AzureResources,
  'azure/app': AzureWebApp,
  'azure/plan': AzurePlan,
  'azure/slots': AzureSlots,
  'azure/autoscale': AzureAutoscale,
  'azure/config': AzureConfig,
  'azure/settings': AzureSettings,
  'azure/hostnames': AzureDomains,
  'azure/ssl': AzureCertificates,
  'azure/deployment-log': AzureDeploymentLog,
  'azure/live-logs': AzureLiveLogs,
}
