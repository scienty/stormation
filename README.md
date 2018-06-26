# stormation
Library for Managing AWS deployments with using cloudformation and boto. It supports splitting deployments into layers and bundle then into one. Bundle has fine grained control over each layer. Each layer templates can import inputs and outputs from dependent layers. Each layer can refer bundle parameters directly in the bundle. It also provide flexibility of running cloudformaiton tempaltes through Jinja rendering. Also there is a plugin support for each layer which can pre process the data that would be provided as context for jinja rendering


## Thanks to
https://github.com/scopely-devops/skew All the inventory folder is imported from skew project and slightly modified to to support integration
